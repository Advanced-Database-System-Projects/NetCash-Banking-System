from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from .models import *


# Regular model registrations
admin.site.register(Roles)
admin.site.register(User)
admin.site.register(Audit_logs)
admin.site.register(Savings_account)
admin.site.register(Savings_transaction)
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