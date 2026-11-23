from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    MyProfileView,
    MySavingsAccountViewSet,
    MySavingsTransactionViewSet,
    MyLoanApplicationViewSet,
    MyLoanViewSet,
    MyLoanPaymentViewSet,
)

router = DefaultRouter()
router.register("savings", MySavingsAccountViewSet, basename="api-savings")
router.register(
    "savings/transactions",
    MySavingsTransactionViewSet,
    basename="api-savings-transactions",
)
router.register(
    "loan-applications",
    MyLoanApplicationViewSet,
    basename="api-loan-applications",
)
router.register("loans", MyLoanViewSet, basename="api-loans")
router.register(
    "loan-payments",
    MyLoanPaymentViewSet,
    basename="api-loan-payments",
)

urlpatterns = [
    path("me/", MyProfileView.as_view(), name="api-my-profile"),
    path("", include(router.urls)),
]
