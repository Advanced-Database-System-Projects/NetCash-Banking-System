
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_dashboard, name="home_dashboard"),
    path("clients/", views.client_list, name="client_list"),
    path("clients/add/", views.client_create, name="client_create"),
    path(
    "clients/<int:client_id>/edit/",
    views.client_update,
    name="client_update"),
    path(
    "clients/<int:client_id>/deactivate/",
    views.client_deactivate,
    name="client_deactivate"),
    path(
    "loans/applications/",
    views.loan_application_list,
    name="loan_application_list"),
    path(
    "loans/apply/",
    views.loan_application_create,
    name="loan_application_create"),
    path(
    "loans/applications/<int:application_id>/",
    views.loan_application_detail,
    name="loan_application_detail"),
    path(
    "loans/applications/<int:application_id>/approve/",
    views.loan_application_approve,
    name="loan_application_approve"),
    path(
    "loans/applications/<int:application_id>/reject/",
    views.loan_application_reject,
    name="loan_application_reject"),
    path("savings/", views.savings_account_list, name="savings_account_list"),
    path("savings/add/", views.savings_account_create, name="savings_account_create"),
    path(
    "savings/<int:account_id>/transaction/",
    views.savings_transaction_create,
    name="savings_transaction_create"),
    path(
    "savings/transactions/",
    views.savings_transaction_list,
    name="savings_transaction_list"),
    path("loans/records/", views.loan_list, name="loan_list"),
    #temporary path for testing
    path("ui-preview/", views.ui_preview, name="ui_preview"),
    path(
    "loans/records/<int:loan_id>/disburse/",
    views.loan_disburse,
    name="loan_disburse"),
    path(
    "loans/records/<int:loan_id>/amortization/",
    views.amortization_list,
    name="amortization_list"),
    path(
    "loans/installments/<int:schedule_id>/payment/",
    views.loan_payment_create,
    name="loan_payment_create"),
    
    path(
    "loans/payments/",
    views.loan_payment_list,
    name="loan_payment_list"
    ),
    path(
    "transactions/records/",
    views.transaction_record_list,
    name="transaction_record_list"),
    path(
    "notifications/",
    views.notification_list,
    name="notification_list"),
    path(
    "borrower/dashboard/",
    views.borrower_dashboard,
    name="borrower_dashboard"),
    path("signup/", views.borrower_signup, name="borrower_signup"),
    path(
    "identity-verification/",
    views.identity_verification_list,
    name="identity_verification_list"),
    path(
    "identity-verification/<int:client_id>/update/",
    views.identity_verification_update,
    name="identity_verification_update"),
    path(
    "borrower/transactions/request/",
    views.borrower_transaction_request,
    name="borrower_transaction_request"),
    path(
    "loans/applications/<int:application_id>/manual-review/",
    views.loan_application_manual_review,
    name="loan_application_manual_review"),
    path(
        "borrower/profile/",
        views.borrower_profile,
        name="borrower_profile"
    ), 
    path("map/", views.map_explorer, name="map_explorer"),

    path(
    "savings/transactions/review/",
    views.savings_transaction_review_list,
    name="savings_transaction_review_list"),

    path(
    "savings/transactions/<int:transaction_id>/review/",
    views.savings_transaction_review,
    name="savings_transaction_review"),
]
