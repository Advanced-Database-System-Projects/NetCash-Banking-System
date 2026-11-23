from rest_framework import generics, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound

from .models import (
    Client_profile,
    Savings_account,
    Savings_transaction,
    Loan_application,
    Loans,
    Loan_payments,
)
from .api_serializers import (
    ClientProfileSerializer,
    SavingsAccountSerializer,
    SavingsTransactionSerializer,
    LoanApplicationSerializer,
    LoanSerializer,
    LoanPaymentSerializer,
)


class MyProfileView(generics.RetrieveAPIView):
    serializer_class = ClientProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        try:
            return Client_profile.objects.get(users=self.request.user)
        except Client_profile.DoesNotExist:
            raise NotFound("No customer profile is linked to this user.")


class MySavingsAccountViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SavingsAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Savings_account.objects.filter(
            client_profile__users=self.request.user
        )


class MySavingsTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SavingsTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Savings_transaction.objects.filter(
            savings_account__client_profile__users=self.request.user
        ).select_related("savings_account")


class MyLoanApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoanApplicationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Loan_application.objects.filter(
            client_profile__users=self.request.user
        ).select_related("client_profile")


class MyLoanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Loans.objects.filter(
            loan_application__client_profile__users=self.request.user
        ).select_related("loan_application")


class MyLoanPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoanPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Loan_payments.objects.filter(
            loans__loan_application__client_profile__users=self.request.user
        ).select_related("loans", "amortization_schedule")
