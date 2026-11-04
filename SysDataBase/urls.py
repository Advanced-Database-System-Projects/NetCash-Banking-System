
from django.urls import path
from . import views

urlpatterns = [
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
]
