from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from .forms import ClientUserForm, ClientProfileForm
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from .models import Client_profile, Roles, Loan_application
from django.http import HttpResponseForbidden
from .forms import LoanApplicationForm
from .models import Loan_application
from django.utils import timezone
from .models import Savings_account
import uuid
from .forms import SavingsAccountForm
from decimal import Decimal, InvalidOperation
from .forms import SavingsTransactionForm
from .models import Savings_account, Savings_transaction
from .models import Loans

@login_required
def ui_preview(request):
    return render(request, "SysDataBase/ui_preview.html")

@login_required
@user_passes_test(lambda user: user.is_staff)
def client_list(request):
    clients = Client_profile.objects.select_related(
        "users"
    ).filter(users__is_active=True  
    ).order_by("last_name", "first_name")

    return render(
        request,
        "SysDataBase/client_list.html",
        {"clients": clients}
    )

@login_required
@user_passes_test(lambda user: user.is_staff)
def client_create(request):
    borrower_role = Roles.objects.get(roles_name="Borrower")

    if request.method == "POST":
        user_form = ClientUserForm(request.POST)
        profile_form = ClientProfileForm(request.POST, request.FILES)

        if user_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                user = user_form.save(commit=False)
                user.roles = borrower_role
                user.is_staff = False
                user.is_superuser = False
                user.save()

                profile = profile_form.save(commit=False)
                profile.users = user
                profile.save()

            messages.success(request, "Client registered successfully.")
            return redirect("client_list")

    else:
        user_form = ClientUserForm()
        profile_form = ClientProfileForm()

    return render(
        request,
        "SysDataBase/client_form.html",
        {
            "user_form": user_form,
            "profile_form": profile_form,
            "is_update": False,
        }
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def client_update(request, client_id):
    client = get_object_or_404(Client_profile, id=client_id)

    if request.method == "POST":
        profile_form = ClientProfileForm(
            request.POST,
            request.FILES,
            instance=client
        )

        if profile_form.is_valid():
            profile_form.save()
            messages.success(
                request,
                "Client information updated successfully."
            )
            return redirect("client_list")

    else:
        profile_form = ClientProfileForm(instance=client)

    return render(
        request,
        "SysDataBase/client_form.html",
        {
            "profile_form": profile_form,
            "user_form": None,
            "is_update": True,
        }
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def client_deactivate(request, client_id):
    client = get_object_or_404(
        Client_profile,
        id=client_id
    )

    user = client.users
    user.is_active = False
    user.save(update_fields=["is_active"])

    messages.success(
        request,
        "Client account deactivated successfully."
    )

    return redirect("client_list")

@login_required
@user_passes_test(lambda user: user.is_staff)
def loan_application_list(request):

    applications = Loan_application.objects.select_related(
        "client_profile",
        "reviewed_by"
    ).order_by("-application_date")

    return render(
        request,
        "SysDataBase/loan_application_list.html",
        {
            "applications": applications
        }
    )

@login_required
def loan_application_create(request):

    # Only borrowers can submit loan applications
    if not request.user.roles or request.user.roles.roles_name != "Borrower":
        return HttpResponseForbidden("Only borrowers can submit loan applications.")

    # Get the logged-in borrower's client profile
    try:
        client = request.user.client_profile
    except Exception:
        return HttpResponseForbidden("No client profile found for this account.")

    if request.method == "POST":
        form = LoanApplicationForm(request.POST)

        if form.is_valid():
            application = form.save(commit=False)
            application.client_profile = client
            application.save()

            messages.success(
                request,
                "Your loan application was submitted successfully."
            )

            return redirect("loan_application_list")

    else:
        form = LoanApplicationForm()

    return render(
        request,
        "SysDataBase/loan_application_form.html",
        {"form": form}
    )

@login_required
@user_passes_test(lambda user: user.is_staff)
def loan_application_detail(request, application_id):

    application = get_object_or_404(
        Loan_application.objects.select_related(
            "client_profile",
            "reviewed_by"
        ),
        id=application_id
    )

    return render(
        request,
        "SysDataBase/loan_application_detail.html",
        {
            "application": application
        }
    )

@login_required
@require_POST
def loan_application_approve(request, application_id):

    if not request.user.roles or request.user.roles.roles_name not in ["Admin", "Loan Officer"]:
        return HttpResponseForbidden("You are not authorized to approve loans.")

    application = get_object_or_404(
        Loan_application,
        id=application_id
    )

    if application.status != "Pending":
        messages.error(request, "This application has already been reviewed.")
        return redirect("loan_application_detail", application_id=application.id)

    # Get the interest rate entered by the Loan Officer
    try:
        interest_rate = Decimal(request.POST.get("annual_interest_rate", ""))
    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Please enter a valid interest rate.")
        return redirect("loan_application_detail", application_id=application.id)

    # Validate the interest rate
    if (
        not interest_rate.is_finite()
        or interest_rate < 0
        or interest_rate > Decimal("999.99")
        or interest_rate.as_tuple().exponent < -2
    ):
        messages.error(request, "Please enter a valid interest rate (0 to 999.99, up to 2 decimal places).")
        return redirect("loan_application_detail", application_id=application.id)

    # Prevent duplicate loan records
    if Loans.objects.filter(loan_application=application).exists():
        messages.error(request, "A loan record already exists for this application.")
        return redirect("loan_application_detail", application_id=application.id)

    # Create the loan record and approve the application together
    with transaction.atomic():

        Loans.objects.create(
            loan_application=application,
            term_months=application.requested_term_months,
            annual_interest_rate=interest_rate,
            principal_amount=application.amount_requested,
            outstanding_balance=application.amount_requested,
            status="Approved"
        )

        application.status = "Approved"
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save()

    messages.success(
        request,
        "Loan application approved and loan record created successfully."
    )

    return redirect("loan_application_detail", application_id=application.id)

@login_required
@require_POST
def loan_application_reject(request, application_id):

    if not request.user.roles or request.user.roles.roles_name not in ["Admin", "Loan Officer"]:
        return HttpResponseForbidden("You are not authorized to reject loans.")

    application = get_object_or_404(
        Loan_application,
        id=application_id
    )

    if application.status != "Pending":
        messages.error(request, "This application has already been reviewed.")
        return redirect("loan_application_detail", application_id=application.id)

    application.status = "Rejected"
    application.reviewed_by = request.user
    application.reviewed_at = timezone.now()
    application.save()

    messages.success(request, "Loan application rejected.")

    return redirect("loan_application_detail", application_id=application.id)

@login_required
@user_passes_test(lambda user: user.is_staff)
def savings_account_list(request):
    accounts = Savings_account.objects.select_related(
        "client_profile"
    ).order_by("-opened_at")

    return render(
        request,
        "SysDataBase/savings_account_list.html",
        {"accounts": accounts}
    )

@login_required
@user_passes_test(lambda user: user.is_staff)
def savings_account_create(request):
    if request.method == "POST":
        form = SavingsAccountForm(request.POST)

        if form.is_valid():
            account = form.save(commit=False)

            # Automatically generate a unique account number
            account.account_no = "SAV" + uuid.uuid4().hex[:12].upper()

            account.save()

            messages.success(
                request,
                "Savings account created successfully."
            )

            return redirect("savings_account_list")

    else:
        form = SavingsAccountForm()

    return render(
        request,
        "SysDataBase/savings_account_form.html",
        {"form": form}
    )

@login_required
@user_passes_test(lambda user: user.is_staff)
def savings_transaction_create(request, account_id):

    account = get_object_or_404(Savings_account, id=account_id)

    if request.method == "POST":
        form = SavingsTransactionForm(request.POST)

        if form.is_valid():
            transaction_type = form.cleaned_data["transaction_type"]
            amount = form.cleaned_data["amount"]

            if amount <= 0:
                messages.error(request, "Amount must be greater than zero.")
            else:
                with transaction.atomic():
                    account = Savings_account.objects.select_for_update().get(
                        id=account_id
                    )

                    if transaction_type == "Withdrawal" and amount > account.current_balance:
                        messages.error(request, "Insufficient savings balance.")
                    else:
                        savings_transaction = form.save(commit=False)
                        savings_transaction.savings_account = account
                        savings_transaction.reference_number = (
                            "TXN" + uuid.uuid4().hex[:12].upper()
                        )
                        savings_transaction.save()

                        if transaction_type == "Deposit":
                            account.current_balance += amount
                        elif transaction_type == "Withdrawal":
                            account.current_balance -= amount

                        account.save()

                        messages.success(
                            request,
                            "Savings transaction recorded successfully."
                        )

                        return redirect("savings_account_list")

    else:
        form = SavingsTransactionForm()

    return render(
        request,
        "SysDataBase/savings_transaction_form.html",
        {"form": form, "account": account}
    )

@login_required
@user_passes_test(lambda user: user.is_staff)
def savings_transaction_list(request):
    transactions = Savings_transaction.objects.select_related(
        "savings_account",
        "savings_account__client_profile"
    ).order_by("-transaction_date")

    return render(
        request,
        "SysDataBase/savings_transaction_list.html",
        {"transactions": transactions}
    )

@login_required
@user_passes_test(lambda user: user.is_staff)
def loan_list(request):
    loans = Loans.objects.select_related(
        "loan_application",
        "loan_application__client_profile"
    ).order_by("-created_at")

    return render(
        request,
        "SysDataBase/loan_list.html",
        {"loans": loans}
    )