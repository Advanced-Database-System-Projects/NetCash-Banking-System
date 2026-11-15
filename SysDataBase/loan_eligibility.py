
from decimal import Decimal, ROUND_HALF_UP, localcontext

from django.utils import timezone

from .models import Loans, Savings_account


MIN_MONTHLY_INCOME = Decimal("10000.00")
MIN_SAVINGS_BALANCE = Decimal("1000.00")
MAX_DEBT_RATIO = Decimal("0.30")

MIN_LOAN_TERM = 3
MAX_LOAN_TERM = 60
MIN_CREDIT_SCORE = 600

RISK_INTEREST_RATES = {
    "Low": Decimal("5.00"),
    "Medium": Decimal("7.00"),
    "High": Decimal("9.00"),
}

def classify_loan_risk(
    income_passed,
    savings_passed,
    credit_score,
    debt_ratio
):
    """
    Classify borrower risk using the project's sample criteria.
    """

    # Insufficient information for a reliable risk assessment
    if credit_score is None:
        return "Manual Review"

    score = 0

    # Income assessment
    if income_passed:
        score += 1

    # Savings assessment
    if savings_passed:
        score += 1

    # Credit history assessment
    if credit_score >= 700:
        score += 2
    elif credit_score >= MIN_CREDIT_SCORE:
        score += 1

    # Repayment capacity assessment
    if debt_ratio <= Decimal("0.20"):
        score += 2
    elif debt_ratio <= MAX_DEBT_RATIO:
        score += 1

    if score >= 5:
        return "Low"
    elif score >= 3:
        return "Medium"
    else:
        return "High"



def calculate_monthly_payment(principal, annual_rate, term_months):
    """Estimate the monthly installment using fixed monthly payments."""

    principal = Decimal(principal)
    annual_rate = Decimal(annual_rate)

    if term_months <= 0 or principal <= 0:
        return Decimal("0.00")

    monthly_rate = annual_rate / Decimal("100") / Decimal("12")

    with localcontext() as context:
        context.prec = 28

        if monthly_rate == 0:
            payment = principal / Decimal(term_months)
        else:
            factor = (Decimal("1") + monthly_rate) ** term_months

            payment = (
                principal * monthly_rate * factor
            ) / (factor - Decimal("1"))

    return payment.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )


def get_existing_monthly_obligations(client):
    """Get the next unpaid installment for each existing loan."""

    active_statuses = [
        Loans.LoanStatus.APPROVED,
        Loans.LoanStatus.ACTIVE,
        Loans.LoanStatus.OVERDUE,
    ]

    existing_loans = Loans.objects.filter(
        loan_application__client_profile=client,
        status__in=active_statuses
    )

    total_obligations = Decimal("0.00")

    for loan in existing_loans:
        schedules = loan.amortization_schedules.exclude(
            status="Paid"
        ).order_by("due_date")

        for schedule in schedules:
            remaining = (
                schedule.total_due - schedule.amount_paid
            )

            if remaining > 0:
                total_obligations += remaining
                break

    return total_obligations.quantize(Decimal("0.01"))


def evaluate_loan_eligibility(application, annual_interest_rate):
    """Evaluate a loan application using the project's sample criteria."""

    client = application.client_profile
    reasons = []
    checks = []

    def add_check(name, passed, details):
        checks.append({
            "name": name,
            "passed": passed,
            "details": details,
        })

        if not passed:
            reasons.append(details)

    # 1. Identity verification
    identity_verified = (
        client.identity_verification_status == "Verified"
    )

    add_check(
        "Identity Verification",
        identity_verified,
        "Identity is verified." if identity_verified
        else "Borrower identity must be verified."
    )

    # 2. Monthly income
    income = client.monthly_income or Decimal("0.00")
    income_passed = income >= MIN_MONTHLY_INCOME

    add_check(
        "Monthly Income",
        income_passed,
        f"Monthly income: PHP {income:,.2f}. "
        f"Minimum required: PHP {MIN_MONTHLY_INCOME:,.2f}."
    )

    # 3. Savings account
    try:
        savings = client.savings_account

        savings_active = (
            savings.status == Savings_account.AccountStatus.ACTIVE
        )

        savings_sufficient = (
            savings.current_balance >= MIN_SAVINGS_BALANCE
        )

        savings_passed = savings_active and savings_sufficient

        savings_details = (
            f"Account status: {savings.status}. "
            f"Balance: PHP {savings.current_balance:,.2f}. "
            f"Minimum required: PHP {MIN_SAVINGS_BALANCE:,.2f}."
        )

    except Savings_account.DoesNotExist:
        savings_passed = False
        savings_details = "Borrower has no savings account."

    add_check(
        "Savings Account",
        savings_passed,
        savings_details
    )

    # 4. Loan term
    term = application.requested_term_months

    term_passed = MIN_LOAN_TERM <= term <= MAX_LOAN_TERM

    add_check(
        "Loan Term",
        term_passed,
        f"Requested term: {term} months. "
        f"Allowed term: {MIN_LOAN_TERM} to {MAX_LOAN_TERM} months."
    )

    # 5. Credit score
    if application.credit_score is None:
        credit_passed = True
        credit_details = "Not Yet Rated. No credit history; no score penalty."
    else:
        credit_passed = application.credit_score >= MIN_CREDIT_SCORE
        credit_details = (
            f"Credit score: {application.credit_score}. "
            f"Minimum sample score: {MIN_CREDIT_SCORE}."
        )

    add_check(
        "Credit History",
        credit_passed,
        credit_details
    )

    # 6. Repayment capacity
    monthly_income = income

    existing_obligations = get_existing_monthly_obligations(client)

    proposed_payment = calculate_monthly_payment(
        application.amount_requested,
        annual_interest_rate,
        term
    )

    total_monthly_obligations = (
        existing_obligations + proposed_payment
    )

    if monthly_income > 0:
        debt_ratio = total_monthly_obligations / monthly_income
    else:
        debt_ratio = Decimal("1.00")

    debt_passed = debt_ratio <= MAX_DEBT_RATIO

    add_check(
        "Repayment Capacity",
        debt_passed,
        (
            f"Estimated new monthly payment: PHP {proposed_payment:,.2f}. "
            f"Existing monthly obligations: PHP {existing_obligations:,.2f}. "
            f"Total: PHP {total_monthly_obligations:,.2f}. "
            f"Debt-to-income ratio: {debt_ratio * 100:.2f}%. "
            f"Maximum allowed: {MAX_DEBT_RATIO * 100:.0f}%."
        )
    )

    
    eligible = all(check["passed"] for check in checks)

    risk_category = classify_loan_risk(
        income_passed=income_passed,
        savings_passed=savings_passed,
        credit_score=application.credit_score,
        debt_ratio=debt_ratio
    )

    recommended_interest_rate = RISK_INTEREST_RATES.get(
        risk_category
    )

    return {
        "eligible": eligible,
        "checks": checks,
        "reasons": reasons,
        "monthly_payment": proposed_payment,
        "existing_obligations": existing_obligations,
        "total_monthly_obligations": total_monthly_obligations,
        "debt_ratio": debt_ratio * 100,
        "risk_category": risk_category,
        "recommended_interest_rate": recommended_interest_rate,
    }

