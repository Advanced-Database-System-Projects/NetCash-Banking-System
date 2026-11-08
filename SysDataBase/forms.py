
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Loan_application
from .models import Savings_account, Savings_transaction


from .models import Client_profile

User = get_user_model()


class ClientUserForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ["username", "email"]


class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = Client_profile
        fields = [
            "first_name",
            "last_name",
            "birth_date",
            "address",
            "monthly_income",
            "phone_number",
            "identification_document",
        ]

        widgets = {
            "birth_date": forms.DateInput(
                attrs={"type": "date"}
            ),
        }
class LoanApplicationForm(forms.ModelForm):
    class Meta:
        model = Loan_application
        fields = [
            "amount_requested",
            "requested_term_months",
            "purpose",
        ]

        widgets = {
            "amount_requested": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Enter loan amount",
                "min": "1",
                "step": "0.01",
            }),
            "requested_term_months": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Enter term in months",
                "min": "1",
            }),
            "purpose": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter loan purpose",
            }),
        }

class SavingsAccountForm(forms.ModelForm):
    class Meta:
        model = Savings_account
        fields = ["client_profile", "annual_interest_rate"]

        widgets = {
            "client_profile": forms.Select(attrs={
                "class": "form-control",
            }),
            "annual_interest_rate": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Enter annual interest rate",
                "min": "0",
                "step": "0.01",
            }),
        }

class SavingsTransactionForm(forms.ModelForm):
    class Meta:
        model = Savings_transaction
        fields = ["transaction_type", "amount"]

        widgets = {
            "transaction_type": forms.Select(attrs={
                "class": "form-control",
            }),
            "amount": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Enter amount",
                "min": "0.01",
                "step": "0.01",
            }),
        }

class LoanApprovalForm(forms.Form):
    annual_interest_rate = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        label="Annual Interest Rate (%)",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Enter annual interest rate",
            "step": "0.01",
            "min": "0",
        })
    )


class BorrowerTransactionRequestForm(forms.ModelForm):

    transaction_type = forms.ChoiceField(
        choices=[
            (
                Savings_transaction.TransactionType.DEPOSIT,
                "Deposit"
            ),
            (
                Savings_transaction.TransactionType.WITHDRAWAL,
                "Withdrawal"
            ),
        ],
        widget=forms.Select(
            attrs={"class": "form-control"}
        )
    )

    class Meta:
        model = Savings_transaction
        fields = ["transaction_type", "amount"]

        widgets = {
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter amount",
                    "min": "0.01",
                    "step": "0.01",
                }
            ),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]

        if amount <= 0:
            raise forms.ValidationError(
                "Amount must be greater than zero."
            )

        return amount
