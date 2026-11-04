
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser


# ==========================================
# BASE MODEL
# ==========================================

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ==========================================
# USER MANAGEMENT
# ==========================================

class Roles(BaseModel):
    roles_name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.roles_name


class User(AbstractUser):
    roles = models.ForeignKey(
        Roles,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users'
    )

    email = models.EmailField(unique=True)

    def __str__(self):
        return self.username


# ==========================================
# AUDIT LOGS
# ==========================================

class Audit_logs(BaseModel):
    users = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=100)
    entity_name = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=50, blank=True)
    action_timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.entity_name}"


# ==========================================
# CLIENT PROFILE
# ==========================================

class Client_profile(BaseModel):
    users = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='client_profile'
    )
    first_name = models.CharField(max_length=45)
    last_name = models.CharField(max_length=45)
    birth_date = models.DateField()
    address = models.CharField(max_length=150)
    monthly_income = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    phone_number = models.CharField(max_length=20)

    identification_document = models.FileField(
        upload_to='client_ids/',
        blank=True,
        null=True
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


# ==========================================
# SAVINGS ACCOUNT
# ==========================================

class Savings_account(BaseModel):

    class AccountStatus(models.TextChoices):
        ACTIVE = 'Active', 'Active'
        INACTIVE = 'Inactive', 'Inactive'
        CLOSED = 'Closed', 'Closed'

    client_profile = models.ForeignKey(
        Client_profile,
        on_delete=models.PROTECT,
        related_name='savings_accounts'
    )

    account_no = models.CharField(max_length=20, unique=True)
    status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE
    )

    current_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    annual_interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )

    opened_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.account_no


# ==========================================
# SAVINGS TRANSACTIONS
# ==========================================

class Savings_transaction(BaseModel):

    class TransactionType(models.TextChoices):
        DEPOSIT = 'Deposit', 'Deposit'
        WITHDRAWAL = 'Withdrawal', 'Withdrawal'
        INTEREST = 'Interest', 'Interest'

    savings_account = models.ForeignKey(
        Savings_account,
        on_delete=models.PROTECT,
        related_name='transactions'
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices
    )

    reference_number = models.CharField(
        max_length=50, unique=True
    )

    amount = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    transaction_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.reference_number


# ==========================================
# LOAN APPLICATION
# ==========================================

class Loan_application(BaseModel):

    class ApplicationStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        APPROVED = 'Approved', 'Approved'
        REJECTED = 'Rejected', 'Rejected'

    client_profile = models.ForeignKey(
        Client_profile,
        on_delete=models.PROTECT,
        related_name='loan_applications'
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications'
    )

    requested_term_months = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING
    )

    purpose = models.CharField(max_length=100)

    amount_requested = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    credit_score = models.IntegerField(
        null=True, blank=True
    )

    eligibility_status = models.CharField(
        max_length=30, blank=True
    )

    application_date = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Application #{self.pk} - {self.client_profile}"


# ==========================================
# LOAN AGREEMENT
# ==========================================

class Loan_agreement(BaseModel):

    loan_application = models.OneToOneField(
        Loan_application,
        on_delete=models.PROTECT,
        related_name='agreement'
    )

    agreement_number = models.CharField(
        max_length=50, unique=True
    )

    agreement_document = models.FileField(
        upload_to='loan_agreements/',
        blank=True,
        null=True
    )

    signed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.agreement_number


# ==========================================
# LOANS
# ==========================================

class Loans(BaseModel):

    class LoanStatus(models.TextChoices):
        APPROVED = 'Approved', 'Approved'
        ACTIVE = 'Active', 'Active'
        PAID = 'Paid', 'Paid'
        OVERDUE = 'Overdue', 'Overdue'

    loan_application = models.OneToOneField(
        Loan_application,
        on_delete=models.PROTECT,
        related_name='loan'
    )

    term_months = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=LoanStatus.choices,
        default=LoanStatus.APPROVED
    )

    annual_interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2
    )

    principal_amount = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    outstanding_balance = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    disbursement_date = models.DateField(
        null=True, blank=True
    )

    def __str__(self):
        return f"Loan #{self.pk}"


# ==========================================
# AMORTIZATION SCHEDULE
# ==========================================

class Amortization_schedule(BaseModel):

    class ScheduleStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        PAID = 'Paid', 'Paid'
        PARTIAL = 'Partial', 'Partial'
        OVERDUE = 'Overdue', 'Overdue'

    loans = models.ForeignKey(
        Loans,
        on_delete=models.PROTECT,
        related_name='amortization_schedules'
    )

    installment_no = models.PositiveIntegerField()
    due_date = models.DateField()

    interest_due = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    principal_due = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    total_due = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    status = models.CharField(
        max_length=20,
        choices=ScheduleStatus.choices,
        default=ScheduleStatus.PENDING
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['loans', 'installment_no'],
                name='unique_loan_installment'
            )
        ]
        ordering = ['installment_no']

    def __str__(self):
        return f"Installment {self.installment_no} - Loan {self.loans_id}"


# ==========================================
# LOAN PAYMENTS
# ==========================================

class Loan_payments(BaseModel):

    class PaymentStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        COMPLETED = 'Completed', 'Completed'
        FAILED = 'Failed', 'Failed'

    loans = models.ForeignKey(
        Loans,
        on_delete=models.PROTECT,
        related_name='payments'
    )

    amortization_schedule = models.ForeignKey(
        Amortization_schedule,
        on_delete=models.PROTECT,
        related_name='payments'
    )

    payment_date = models.DateField()
    amount = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )

    payment_method = models.CharField(max_length=45)

    reference_number = models.CharField(
        max_length=50, unique=True
    )

    def __str__(self):
        return self.reference_number


# ==========================================
# TRANSACTION RECORDS
# ==========================================

class Transaction_records(BaseModel):

    savings_transaction = models.ForeignKey(
        Savings_transaction,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='accounting_records'
    )

    loan_payment = models.ForeignKey(
        Loan_payments,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='accounting_records'
    )

    entry_date = models.DateTimeField(auto_now_add=True)

    debit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    credit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    entry_type = models.CharField(max_length=45)

    account_code = models.CharField(max_length=45)

    def __str__(self):
        return self.account_code


# ==========================================
# NOTIFICATIONS
# ==========================================

class Notifications(BaseModel):

    class Channel(models.TextChoices):
        EMAIL = 'Email', 'Email'
        SMS = 'SMS', 'SMS'

    class NotificationStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        SENT = 'Sent', 'Sent'
        FAILED = 'Failed', 'Failed'

    users = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='notifications'
    )

    channel = models.CharField(
        max_length=20,
        choices=Channel.choices
    )

    status = models.CharField(
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING
    )

    message = models.TextField()

    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.channel} - {self.status}"
