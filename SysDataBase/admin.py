from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from .models import *

from .savings_service import (
    review_savings_transaction,
    SavingsReviewError,
)

from .models import (
    Savings_transaction,
    Savings_account,
    Transaction_records,
)

# Regular model registrations
admin.site.register(Roles)
admin.site.register(User)
@admin.register(Audit_logs)
class AuditLogReadOnlyAdmin(admin.ModelAdmin):
    list_display = ("action_timestamp", "users", "action", "entity_name", "entity_id")
    list_filter = ("action", "entity_name", "action_timestamp")
    search_fields = ("users__username", "action", "entity_name", "entity_id")
    ordering = ("-action_timestamp",)

    def has_view_permission(self, request, obj=None):
        user = request.user
        role = user.roles.roles_name if user.is_authenticated and user.roles_id else None
        return user.is_authenticated and user.is_staff and (user.is_superuser or role == "Admin")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(Savings_account)
admin.site.register(Loan_application)
admin.site.register(Loan_agreement)
admin.site.register(Loans)
admin.site.register(Amortization_schedule)
admin.site.register(Loan_payments)
admin.site.register(Transaction_records)
admin.site.register(Notifications)


# Client Profile Admin
@admin.register(Client_profile)
class ClientProfileAdmin(admin.ModelAdmin):

    list_display = (
        "first_name",
        "last_name",
        "identity_verification_status",
        "verified_by",
        "verified_at",
    )

    list_filter = ("identity_verification_status",)

    search_fields = (
        "first_name",
        "last_name",
        "users__username",
    )

    readonly_fields = (
        "verified_by",
        "verified_at",
    )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():

            if obj.identity_verification_status == (
                Client_profile.VerificationStatus.VERIFIED
            ):
                obj.verified_by = request.user
                obj.verified_at = timezone.now()
            else:
                obj.verified_by = None
                obj.verified_at = None

            super().save_model(request, obj, form, change)

            try:
                savings = Savings_account.objects.select_for_update().get(
                    client_profile=obj
                )

                if obj.identity_verification_status == (
                    Client_profile.VerificationStatus.VERIFIED
                ):
                    savings.status = Savings_account.AccountStatus.ACTIVE

                elif obj.identity_verification_status == (
                    Client_profile.VerificationStatus.REJECTED
                ):
                    savings.status = Savings_account.AccountStatus.INACTIVE

                else:
                    savings.status = (
                        Savings_account.AccountStatus.PENDING_VERIFICATION
                    )

                savings.save(update_fields=["status", "updated_at"])

            except Savings_account.DoesNotExist:
                messages.warning(
                    request,
                    "Client profile saved, but no savings account was found."
                )


# Loan Application History Admin
@admin.register(LoanApplicationHistory)
class LoanApplicationHistoryAdmin(admin.ModelAdmin):

    list_display = (
        "application",
        "performed_by",
        "action",
        "previous_status",
        "new_status",
        "created_at",
    )

    list_filter = ("action", "created_at")

    search_fields = (
        "application__id",
        "performed_by__username",
        "details",
    )

    readonly_fields = (
        "application",
        "performed_by",
        "action",
        "previous_status",
        "new_status",
        "details",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_authenticated
            and request.user.is_staff
            and (
                request.user.is_superuser
                or (
                    request.user.roles
                    and request.user.roles.roles_name == "Admin"
                )
            )
        )



class SavingsTransactionAdminForm(forms.ModelForm):
    class Meta:
        model = Savings_transaction
        fields = "__all__"

    def clean_status(self):
        status = self.cleaned_data["status"]

        if not self.instance.pk:
            raise forms.ValidationError(
                "Create transactions through the banking portal."
            )

        old = Savings_transaction.objects.get(
            pk=self.instance.pk
        )

        # Completed transactions cannot be changed again.
        if old.status != Savings_transaction.TransactionStatus.PENDING:
            if status != old.status:
                raise forms.ValidationError(
                    "This transaction has already been reviewed."
                )
            return status

        allowed = [
            Savings_transaction.TransactionStatus.PENDING,
            Savings_transaction.TransactionStatus.APPROVED,
            Savings_transaction.TransactionStatus.REJECTED,
        ]

        if status not in allowed:
            raise forms.ValidationError(
                "Select Pending, Approved, or Rejected."
            )

        if status == Savings_transaction.TransactionStatus.APPROVED:
            account = old.savings_account

            if account.status != Savings_account.AccountStatus.ACTIVE:
                raise forms.ValidationError(
                    "The savings account must be active."
                )

            if Transaction_records.objects.filter(
                savings_transaction=old
            ).exists():
                raise forms.ValidationError(
                    "This transaction already has ledger entries."
                )

            if old.transaction_type not in [
                Savings_transaction.TransactionType.DEPOSIT,
                Savings_transaction.TransactionType.WITHDRAWAL,
            ]:
                raise forms.ValidationError(
                    "This transaction type requires a separate process."
                )

            if old.amount <= 0:
                raise forms.ValidationError(
                    "The transaction amount must be positive."
                )

            if (
                old.transaction_type
                == Savings_transaction.TransactionType.WITHDRAWAL
                and old.amount > account.current_balance
            ):
                raise forms.ValidationError(
                    "Insufficient savings balance."
                )

        return status


@admin.register(Savings_transaction)
class SavingsTransactionAdmin(admin.ModelAdmin):

    form = SavingsTransactionAdminForm

    list_display = (
        "reference_number",
        "savings_account",
        "transaction_type",
        "amount",
        "status",
        "transaction_date",
    )

    list_filter = ("status", "transaction_type")

    search_fields = (
        "reference_number",
        "savings_account__account_no",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = (
            "savings_account",
            "transaction_type",
            "reference_number",
            "amount",
            "transaction_date",
        )

        if obj and obj.status != Savings_transaction.TransactionStatus.PENDING:
            return fields + ("status",)

        return fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        role = (
            request.user.roles.roles_name
            if getattr(request.user, "roles", None)
            else None
        )

        authorized = (
            request.user.is_active
            and request.user.is_staff
            and (
                request.user.is_superuser
                or role == "Admin"
            )
        )

        return authorized and super().has_change_permission(
            request, obj
        )

    
    def save_model(self, request, obj, form, change):
        if not change:
            raise PermissionDenied(
                "Transactions cannot be created here."
            )

        old = Savings_transaction.objects.get(pk=obj.pk)

        # Already reviewed transactions cannot be processed again.
        if old.status != Savings_transaction.TransactionStatus.PENDING:
            if obj.status != old.status:
                raise PermissionDenied(
                    "This transaction has already been reviewed."
                )
            return

        # Nothing to process if status remains Pending.
        if obj.status == Savings_transaction.TransactionStatus.PENDING:
            return

        if obj.status == Savings_transaction.TransactionStatus.APPROVED:
            decision = "approve"

        elif obj.status == Savings_transaction.TransactionStatus.REJECTED:
            decision = "reject"

        else:
            raise PermissionDenied(
                "Invalid transaction status."
            )

        try:
            review_savings_transaction(
                transaction_id=obj.pk,
                decision=decision
            )

        except SavingsReviewError as exc:
            raise PermissionDenied(str(exc))

        # Refresh the object after the service updates the database.
        obj.refresh_from_db()

