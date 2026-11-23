"""Rule-based loan decisions for the BankingSys academic prototype.

Only proven internal repayment history permits the automatic route.  Missing
credit information is never guessed or filled with an invented score.
"""
from decimal import Decimal

from .loan_eligibility import (
    MAX_DEBT_RATIO,
    RISK_INTEREST_RATES,
    calculate_monthly_payment,
    evaluate_loan_eligibility,
    get_existing_monthly_obligations,
)
from .models import Amortization_schedule, Loan_application, Loans


class LoanDecision:
    AUTO_APPROVAL_CANDIDATE = "Auto-Approval Candidate"
    MANUAL_REVIEW = "Needs Manual Review"
    READY_FOR_MANUAL_APPROVAL = "Ready for Manual Approval"
    NOT_ELIGIBLE = "Not Eligible"


# Conservative DEMO policy; not an actual financial institution's policy.
# Set False to pause automatic approvals while retaining classification.
DEMO_AUTOMATIC_APPROVAL_ENABLED = True
MAX_AUTOMATIC_AMOUNT = Decimal("20000.00")
MAX_SAVINGS_BASED_AMOUNT = Decimal("3000.00")
MAX_AUTOMATIC_TERM = 12


def has_verified_internal_repayment_history(client):
    """Require a genuinely fully paid prior loan recorded in BankingSys."""
    paid_loans = Loans.objects.filter(
        loan_application__client_profile=client,
        status=Loans.LoanStatus.PAID,
        outstanding_balance__lte=Decimal("0.00"),
    ).prefetch_related("amortization_schedules")

    for loan in paid_loans:
        schedules = list(loan.amortization_schedules.all())
        if (
            schedules
            and len(schedules) == loan.term_months
            and all(
                s.status == Amortization_schedule.ScheduleStatus.PAID
                and s.total_due > 0
                and s.amount_paid >= s.total_due
                for s in schedules
            )
        ):
            return True
    return False


def evaluate_automatic_loan_decision(application):
    """Classify without changing the database or granting any loan."""
    base = evaluate_loan_eligibility(application)
    failed_prerequisites = [
        check["details"]
        for check in base["checks"]
        if not check["passed"] and check["name"] != "Repayment Capacity"
    ]

    if application.status != Loan_application.ApplicationStatus.PENDING:
        return {
            "decision": LoanDecision.MANUAL_REVIEW,
            "eligibility": base,
            "reasons": ["Application is no longer pending."],
        }

    # A failed identity, savings, term, income, or scored-credit check
    # cannot be bypassed by the internal-repayment path.
    if failed_prerequisites:
        return {
            "decision": LoanDecision.NOT_ELIGIBLE,
            "eligibility": base,
            "reasons": failed_prerequisites,
        }

    if application.credit_score is None:
        review_completed = (
            application.risk_review_status
            == Loan_application.RiskReviewStatus.COMPLETED
            and application.risk_category in {"Low", "Medium", "High"}
            and application.manually_recommended_rate is not None
        )
        if review_completed:
            if base["eligible"]:
                return {
                    "decision": LoanDecision.READY_FOR_MANUAL_APPROVAL,
                    "eligibility": base,
                    "reasons": ["Completed human risk review; staff approval required."],
                }
            return {
                "decision": LoanDecision.NOT_ELIGIBLE,
                "eligibility": base,
                "reasons": base["reasons"],
            }

        client = application.client_profile
        has_prior_paid_loan = has_verified_internal_repayment_history(client)
        # Small loans can also qualify via internal savings evidence. No
        # savings are held/reserved here: academic demo, not production.
        savings = client.savings_account
        savings_based_candidate = (
            application.amount_requested <= MAX_SAVINGS_BASED_AMOUNT
            and savings.current_balance >= application.amount_requested * 2
        )
        no_open_loans = not Loans.objects.filter(
            loan_application__client_profile=client,
            status__in=[
                Loans.LoanStatus.APPROVED,
                Loans.LoanStatus.ACTIVE,
                Loans.LoanStatus.OVERDUE,
            ],
        ).exists()
        income = client.monthly_income or Decimal("0.00")
        amount = application.amount_requested
        amount_ok = (
            amount > 0
            and amount <= MAX_AUTOMATIC_AMOUNT
            and amount <= income
        )
        term_ok = 3 <= application.requested_term_months <= MAX_AUTOMATIC_TERM
        active_user = client.users.is_active

        if (has_prior_paid_loan or savings_based_candidate) and no_open_loans and amount_ok and term_ok and active_user:
            rate = RISK_INTEREST_RATES["Low"]
            payment = calculate_monthly_payment(
                amount, rate, application.requested_term_months
            )
            obligations = get_existing_monthly_obligations(client)
            total = obligations + payment
            if income > 0 and total / income <= MAX_DEBT_RATIO:
                return {
                    "decision": LoanDecision.AUTO_APPROVAL_CANDIDATE,
                    "eligibility": base,
                    "interest_rate": rate,
                    "reasons": [
                        "Identity, income, savings and term prerequisites passed.",
                        (
                            "Prior loan is fully repaid in internal records."
                            if has_prior_paid_loan
                            else "Small loan: internal savings balance is at least twice the requested amount."
                        ),
                        "No currently open loan; amount and term within demo limits.",
                        "Projected repayment is within the 30% debt-to-income limit.",
                        "Internal history used; no credit score was invented.",
                    ],
                }

        return {
            "decision": LoanDecision.MANUAL_REVIEW,
            "eligibility": base,
            "reasons": [
                "No qualifying internal savings evidence or fully paid prior loan.",
                "An authorized staff member must review this application.",
            ],
        }

    # There is no field recording who verified an external credit score.
    # Do not automatically approve based on a potentially unverified value.
    return {
        "decision": (
            LoanDecision.READY_FOR_MANUAL_APPROVAL
            if base["eligible"]
            else LoanDecision.NOT_ELIGIBLE
        ),
        "eligibility": base,
        "reasons": (
            ["Staff must confirm the credit score source before approving."]
            if base["eligible"] else base["reasons"]
        ),
    }
