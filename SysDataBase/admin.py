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