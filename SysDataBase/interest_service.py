
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import (
    Savings_account,
    Savings_transaction,
    Transaction_records,
)


def calculate_monthly_interest(account):
    """
    Calculate one month's interest using the annual interest rate.
    """

    monthly_rate = (
        account.annual_interest_rate / Decimal("100")
    ) / Decimal("12")

    interest = (
        account.current_balance * monthly_rate
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    return interest


def credit_monthly_interest(account_id, year=None, month=None):
    """
    Credit monthly interest once per account per calendar month.
    """

    now = timezone.now()

    year = year or now.year
    month = month or now.month

    with transaction.atomic():

        account = Savings_account.objects.select_for_update().get(
            id=account_id
        )

        if account.status != Savings_account.AccountStatus.ACTIVE:
            return {
                "success": False,
                "message": "Account is not active."
            }

        reference = f"INT-{account.id}-{year}{month:02d}"

        already_credited = Savings_transaction.objects.filter(
            savings_account=account,
            reference_number=reference
        ).exists()

        if already_credited:
            return {
                "success": False,
                "message": "Interest has already been credited for this month."
            }

        interest = calculate_monthly_interest(account)

        if interest <= Decimal("0.00"):
            return {
                "success": False,
                "message": "No interest to credit."
            }

        savings_transaction = Savings_transaction.objects.create(
            savings_account=account,
            transaction_type=Savings_transaction.TransactionType.INTEREST,
            reference_number=reference,
            amount=interest,
            status=Savings_transaction.TransactionStatus.APPROVED
        )

        account.current_balance += interest
        account.save()

        Transaction_records.objects.create(
            savings_transaction=savings_transaction,
            debit_amount=interest,
            credit_amount=Decimal("0.00"),
            entry_type="Savings Interest",
            account_code="INTEREST_EXPENSE"
        )

        Transaction_records.objects.create(
            savings_transaction=savings_transaction,
            debit_amount=Decimal("0.00"),
            credit_amount=interest,
            entry_type="Savings Interest",
            account_code="SAVINGS_LIABILITY"
        )

        return {
            "success": True,
            "interest": interest,
            "new_balance": account.current_balance,
            "message": "Monthly interest credited successfully."
        }
