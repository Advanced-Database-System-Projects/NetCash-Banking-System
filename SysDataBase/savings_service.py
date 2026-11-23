
from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError

from .models import (
    Savings_account,
    Savings_transaction,
    Transaction_records,
)
from .notifications import notify


class SavingsReviewError(Exception):
    """Raised when a savings request cannot be reviewed."""
    pass


@transaction.atomic
def review_savings_transaction(transaction_id, decision):
    """
    Review a pending savings transaction.

    Both Django Admin and the Management Portal
    must call this function.
    """

    if decision not in ["approve", "reject"]:
        raise SavingsReviewError("Invalid review decision.")

    txn = (
        Savings_transaction.objects
        .select_for_update()
        .get(pk=transaction_id)
    )

    if txn.status != Savings_transaction.TransactionStatus.PENDING:
        raise SavingsReviewError(
            "This transaction has already been reviewed."
        )

    account = (
        Savings_account.objects
        .select_for_update()
        .select_related("client_profile__users")
        .get(pk=txn.savings_account_id)
    )

    if not txn.amount.is_finite() or txn.amount <= 0:
        raise SavingsReviewError(
            "Transaction amount must be positive."
        )

    if txn.amount.as_tuple().exponent < -2:
        raise SavingsReviewError(
            "Transaction amount cannot exceed two decimal places."
        )

    if Transaction_records.objects.filter(
        savings_transaction=txn
    ).exists():
        raise SavingsReviewError(
            "Existing ledger records require investigation."
        )

    if decision == "approve":

        if account.status != Savings_account.AccountStatus.ACTIVE:
            raise SavingsReviewError(
                "The savings account is not active."
            )

        if txn.transaction_type == Savings_transaction.TransactionType.DEPOSIT:

            new_balance = account.current_balance + txn.amount

            debit_code = "CASH"
            credit_code = "SAVINGS_LIABILITY"
            entry_type = "Savings Deposit"

        elif txn.transaction_type == Savings_transaction.TransactionType.WITHDRAWAL:

            if txn.amount > account.current_balance:
                raise SavingsReviewError(
                    "Insufficient savings balance."
                )

            new_balance = account.current_balance - txn.amount

            debit_code = "SAVINGS_LIABILITY"
            credit_code = "CASH"
            entry_type = "Savings Withdrawal"

        else:
            raise SavingsReviewError(
                "Unsupported transaction type."
            )

        # Update the account balance.
        account.current_balance = new_balance

        account.save(
            update_fields=["current_balance", "updated_at"]
        )

        # Debit entry.
        Transaction_records.objects.create(
            savings_transaction=txn,
            debit_amount=txn.amount,
            credit_amount=Decimal("0.00"),
            entry_type=entry_type,
            account_code=debit_code,
        )

        # Credit entry.
        Transaction_records.objects.create(
            savings_transaction=txn,
            debit_amount=Decimal("0.00"),
            credit_amount=txn.amount,
            entry_type=entry_type,
            account_code=credit_code,
        )

        txn.status = Savings_transaction.TransactionStatus.APPROVED

    else:
        txn.status = Savings_transaction.TransactionStatus.REJECTED

    txn.save(update_fields=["status", "updated_at"])

    # Capture values before the transaction ends.
    borrower = account.client_profile.users
    amount = txn.amount
    txn_type = txn.transaction_type
    reference = txn.reference_number
    final_status = txn.status

    def send_notification():
        notify(
            borrower,
            (
                f"Your {txn_type.lower()} request of "
                f"PHP {amount:,.2f} ({reference}) "
                f"has been {final_status.lower()}."
            ),
            subject=f"Savings Transaction {final_status}",
        )

    # Notify only if the database transaction succeeds.
    transaction.on_commit(
        send_notification,
        robust=True
    )

    return txn
