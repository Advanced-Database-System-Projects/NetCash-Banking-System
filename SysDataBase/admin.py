from django.contrib import admin
from .models import *

admin.site.register(Roles)
admin.site.register(User)
admin.site.register(Audit_logs)
admin.site.register(Client_profile)
admin.site.register(Savings_account)
admin.site.register(Savings_transaction)
admin.site.register(Loan_application)
admin.site.register(Loan_agreement)
admin.site.register(Loans)
admin.site.register(Amortization_schedule)
admin.site.register(Loan_payments)
admin.site.register(Transaction_records)
admin.site.register(Notifications)
@admin.register(LoanApplicationHistory)
class LoanApplicationHistoryAdmin(admin.ModelAdmin):

    list_display = (
        'application',
        'performed_by',
        'action',
        'previous_status',
        'new_status',
        'created_at',
    )

    list_filter = ('action', 'created_at')

    search_fields = (
        'application__id',
        'performed_by__username',
        'details',
    )

    readonly_fields = (
        'application',
        'performed_by',
        'action',
        'previous_status',
        'new_status',
        'details',
        'created_at',
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