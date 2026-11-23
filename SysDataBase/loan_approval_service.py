"""Shared approval process for the BankingSys academic prototype."""
from django.db import transaction
from django.utils import timezone

from .loan_decision_service import LoanDecision, evaluate_automatic_loan_decision
from .loan_eligibility import evaluate_loan_eligibility
from .models import Loan_agreement, Loan_application, Loans, LoanApplicationHistory


class LoanApprovalError(Exception):
    pass


def approve_loan_application(
    application_id,
    generate_agreement,
    approved_by=None,
    approval_source="manual",
):
    """Approve once with an audit trail. Does NOT disburse any money.

    The database one-to-one constraints are the final duplicate protection.
    select_for_update is advisory on SQLite (SQLite does not row-lock).
    """
    if approval_source not in ("manual", "automatic"):
        raise LoanApprovalError("Unknown approval source.")

    if approval_source == "manual":
        role = getattr(getattr(approved_by, "roles", None), "roles_name", None)
        if not (approved_by and approved_by.is_staff and role in ("Admin", "Loan Officer")):
            raise LoanApprovalError("Only authorized staff may manually approve loans.")

    with transaction.atomic():
        application = Loan_application.objects.select_for_update().get(pk=application_id)
        if application.status != Loan_application.ApplicationStatus.PENDING:
            raise LoanApprovalError("Application is no longer pending.")
        if Loans.objects.filter(loan_application=application).exists():
            raise LoanApprovalError("A loan record already exists.")
        if Loan_agreement.objects.filter(loan_application=application).exists():
            raise LoanApprovalError("A loan agreement already exists.")

        if approval_source == "automatic":
            assessment = evaluate_automatic_loan_decision(application)
            if assessment["decision"] != LoanDecision.AUTO_APPROVAL_CANDIDATE:
                raise LoanApprovalError("Application does not qualify for automatic approval.")
            rate = assessment["interest_rate"]
        else:
            eligibility = evaluate_loan_eligibility(application)
            if not eligibility["eligible"]:
                raise LoanApprovalError("Eligibility requirements are not satisfied.")
            rate = eligibility["recommended_interest_rate"]
            if rate is None:
                raise LoanApprovalError("Interest rate / manual risk review is missing.")

        loan = Loans.objects.create(
            loan_application=application,
            term_months=application.requested_term_months,
            annual_interest_rate=rate,
            principal_amount=application.amount_requested,
            outstanding_balance=application.amount_requested,
            status=Loans.LoanStatus.APPROVED,
        )
        generate_agreement(application, loan)

        application.status = Loan_application.ApplicationStatus.APPROVED
        application.reviewed_by = approved_by
        application.reviewed_at = timezone.now()
        application.eligibility_status = (
            "Auto-Approved" if approval_source == "automatic"
            else application.eligibility_status
        )
        application.save(update_fields=[
            "status", "reviewed_by", "reviewed_at", "eligibility_status",
        ])
        LoanApplicationHistory.objects.create(
            application=application,
            action=LoanApplicationHistory.ActionType.APPROVED,
            performed_by=approved_by,
            previous_status="Pending",
            new_status="Approved",
            details=(
                f"Rule-based {approval_source} approval; "
                f"annual interest rate {rate}%; "
                "loan created, agreement generated; not yet disbursed."
            ),
        )
        return loan
