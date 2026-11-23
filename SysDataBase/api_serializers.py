from rest_framework import serializers
from .models import (
    Client_profile,
    Savings_account,
    Savings_transaction,
    Loan_application,
    Loans,
    Loan_payments,
)


class ClientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client_profile
        fields = (
            "id", "first_name", "last_name", "birth_date",
            "address", "phone_number", "identity_verification_status",
        )


class SavingsAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Savings_account
        fields = (
            "id", "account_no", "status", "current_balance",
            "annual_interest_rate", "opened_at",
        )


class SavingsTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Savings_transaction
        fields = (
            "id", "transaction_type", "reference_number",
            "amount", "status", "transaction_date",
        )


class LoanApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan_application
        fields = (
            "id", "requested_term_months", "status", "purpose",
            "amount_requested", "eligibility_status",
            "risk_review_status", "risk_category", "application_date",
        )


class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loans
        fields = (
            "id", "term_months", "status", "annual_interest_rate",
            "principal_amount", "outstanding_balance", "disbursement_date",
        )


class LoanPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan_payments
        fields = (
            "id", "payment_date", "amount", "status",
            "payment_method", "reference_number",
        )
