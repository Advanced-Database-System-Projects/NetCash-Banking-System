from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from .forms import ClientUserForm, ClientProfileForm
from django.views.decorators.http import require_POST
from .models import Amortization_schedule, Client_profile, Roles, Loan_application
from django.http import HttpResponseForbidden
from .forms import LoanApplicationForm
from .models import Loan_application
from django.utils import timezone
from .models import Savings_account
import uuid
from .forms import SavingsAccountForm
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from .forms import SavingsTransactionForm
from .models import Savings_account, Savings_transaction
from .models import Loans, Loan_payments
from io import BytesIO
from django.core.files.base import ContentFile
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from .models import Loan_agreement
from django.contrib.auth import authenticate, login
import calendar
from datetime import date
from django.utils.dateparse import parse_date
from .models import Transaction_records
from .models import Notifications
from django.db.models import Q
from django.db.models import Sum
from .payment_gateway import simulate_payment
from .forms import BorrowerTransactionRequestForm
from .models import LoanApplicationHistory
from .notifications import notify_loan_decision
from .loan_decision_service import evaluate_automatic_loan_decision
from django.db import IntegrityError

from .loan_approval_service import (
    approve_loan_application,
    LoanApprovalError,
)

def borrower_signup(request):

    borrower_role, created = Roles.objects.get_or_create(
        roles_name="Borrower"
    )

    if request.method == "POST":
        user_form = ClientUserForm(request.POST)
        profile_form = ClientProfileForm(
            request.POST,
            request.FILES
        )

        if user_form.is_valid() and profile_form.is_valid():

            with transaction.atomic():

                # Create borrower user
                user = user_form.save(commit=False)
                user.roles = borrower_role
                user.is_staff = False
                user.is_superuser = False
                user.save()

                # Create client profile
                profile = profile_form.save(commit=False)
                profile.users = user
                profile.identity_verification_status = (
                    Client_profile.VerificationStatus.PENDING
                )
                profile.save()

                # Automatically create savings account
                Savings_account.objects.create(
                    client_profile=profile,
                    account_no="SAV" + uuid.uuid4().hex[:12].upper(),
                    status=(
                        Savings_account.AccountStatus.PENDING_VERIFICATION
                    ),
                    current_balance=Decimal("0.00"),
                    annual_interest_rate=Decimal("0.00")
                )

            messages.success(
                request,
                "Registration successful! You may now log in."
            )

            return redirect("user_login")

    else:
        user_form = ClientUserForm()
        profile_form = ClientProfileForm()

    return render(
        request,
        "SysDataBase/borrower_signup.html",
        {
            "user_form": user_form,
            "profile_form": profile_form,
        }
    )

def user_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("home_dashboard")
            else:
                messages.error(request, "Your account is inactive.")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "SysDataBase/login.html")

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
def identity_verification_list(request):
    role = request.user.roles.roles_name if request.user.roles else None

    if not request.user.is_staff or role not in ["Admin", "Staff"]:
        return HttpResponseForbidden(
            "You are not authorized to review identities."
        )

    pending_clients = Client_profile.objects.filter(
        identity_verification_status=(
            Client_profile.VerificationStatus.PENDING
        )
    ).select_related("users").order_by("-created_at")

    return render(
        request,
        "SysDataBase/identity_verification_list.html",
        {"pending_clients": pending_clients}
    )


@login_required
@require_POST
def identity_verification_update(request, client_id):
    role = request.user.roles.roles_name if request.user.roles else None

    if not request.user.is_staff or role not in ["Admin", "Staff"]:
        return HttpResponseForbidden(
            "You are not authorized to review identities."
        )

    client = get_object_or_404(Client_profile, id=client_id)

    if client.identity_verification_status != (
        Client_profile.VerificationStatus.PENDING
    ):
        messages.error(request, "This identity has already been reviewed.")
        return redirect("identity_verification_list")

    action = request.POST.get("action")
    notes = request.POST.get("verification_notes", "").strip()

    if action not in ["approve", "reject"]:
        messages.error(request, "Invalid verification action.")
        return redirect("identity_verification_list")

    try:
        with transaction.atomic():
            account = Savings_account.objects.select_for_update().get(
                client_profile=client
            )

            client.verified_by = request.user
            client.verification_notes = notes
            client.verified_at = (
                timezone.now() if action == "approve" else None
            )

            if action == "approve":
                client.identity_verification_status = (
                    Client_profile.VerificationStatus.VERIFIED
                )
                account.status = Savings_account.AccountStatus.ACTIVE
                success_message = (
                    "Identity verified. Savings account is now active."
                )
            else:
                client.identity_verification_status = (
                    Client_profile.VerificationStatus.REJECTED
                )
                account.status = Savings_account.AccountStatus.INACTIVE
                success_message = (
                    "Identity rejected. Savings account is now inactive."
                )

            client.save()
            account.save(update_fields=["status", "updated_at"])

    except Savings_account.DoesNotExist:
        messages.error(
            request,
            "No savings account was found for this borrower."
        )
        return redirect("identity_verification_list")

    messages.success(request, success_message)
    return redirect("identity_verification_list")


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


# RULE: ONE ACTIVE LOAN PER BORROWER
# Pending application => block. Any loan that is not both Paid AND zero-balance
# => block. Rejected applications and fully settled loans do not block.
def get_loan_application_block_reason(client):
    if Loan_application.objects.filter(
        client_profile=client,
        status=Loan_application.ApplicationStatus.PENDING,
    ).exists():
        return (
            "You already have a pending loan application. "
            "Please wait for its decision before applying again."
        )

    # An inconsistent record (e.g., Paid but outstanding balance remains)
    # must not be treated as fully settled.
    unsettled = Loans.objects.filter(
        loan_application__client_profile=client,
    ).exclude(
        status=Loans.LoanStatus.PAID,
        outstanding_balance__lte=Decimal("0.00"),
    )
    if unsettled.exists():
        return (
            "You already have a loan that is not fully settled. "
            "You can apply again after it is marked Paid with zero balance."
        )

    # Protect against an old approved application without a matching loan row.
    if Loan_application.objects.filter(
        client_profile=client,
        status=Loan_application.ApplicationStatus.APPROVED,
        loan__isnull=True,
    ).exists():
        return (
            "Your previous approved application needs to be reconciled "
            "by staff before you can apply again."
        )

    return None


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

    # Check the rule even when borrower opens the application form directly.
    block_reason = get_loan_application_block_reason(client)
    if block_reason:
        messages.warning(request, block_reason)
        return redirect("borrower_dashboard")

    if request.method == "POST":
        form = LoanApplicationForm(request.POST)

        if form.is_valid():
            
            application = form.save(commit=False)
            application.client_profile = client

            from django.db import IntegrityError
            from .loan_decision_service import (
                LoanDecision, DEMO_AUTOMATIC_APPROVAL_ENABLED,
                evaluate_automatic_loan_decision,
            )
            from .loan_approval_service import (
                LoanApprovalError, approve_loan_application,
            )

            with transaction.atomic():
                # Force a write on the borrower's profile to serialize
                # submissions on SQLite (which ignores select_for_update).
                Client_profile.objects.filter(pk=client.pk).update(
                    updated_at=timezone.now()
                )
                block_reason = get_loan_application_block_reason(client)
                if block_reason:
                    messages.error(request, block_reason)
                    return redirect("borrower_dashboard")
                application.save()
                record_loan_application_history(
                    application=application,
                    action=LoanApplicationHistory.ActionType.SUBMITTED,
                    performed_by=request.user,
                    previous_status="",
                    new_status="Pending",
                    details="Borrower submitted a new loan application.",
                )

                result = evaluate_automatic_loan_decision(application)
                application.eligibility_status = result["decision"]
                application.save(update_fields=["eligibility_status"])
                record_loan_application_history(
                    application=application,
                    action=LoanApplicationHistory.ActionType.UPDATED,
                    performed_by=None,
                    previous_status="Pending",
                    new_status="Pending",
                    details=(
                        "Rule-based preliminary classification: "
                        + result["decision"] + ". "
                        + " | ".join(result["reasons"])
                    ),
                )

                if (DEMO_AUTOMATIC_APPROVAL_ENABLED
                        and result["decision"] == LoanDecision.AUTO_APPROVAL_CANDIDATE):
                    try:
                        # Savepoint: failure leaves a pending application to review.
                        with transaction.atomic():
                            approve_loan_application(
                                application_id=application.id,
                                generate_agreement=generate_loan_agreement,
                                approved_by=None,
                                approval_source="automatic",
                            )
                    except (LoanApprovalError, IntegrityError) as exc:
                        application.refresh_from_db()
                        application.eligibility_status = LoanDecision.MANUAL_REVIEW
                        application.save(update_fields=["eligibility_status"])
                        record_loan_application_history(
                            application=application,
                            action=LoanApplicationHistory.ActionType.UPDATED,
                            performed_by=None,
                            previous_status="Pending",
                            new_status="Pending",
                            details=f"Automatic approval stopped; staff review required: {exc}",
                        )

            application.refresh_from_db()
            if application.status == Loan_application.ApplicationStatus.APPROVED:
                messages.success(
                    request,
                    "Your loan was automatically approved under the demo rules. "
                    "Disbursement is a separate process.",
                )
            else:
                messages.success(
                    request,
                    "Your loan application was submitted for rule-based evaluation. "
                    "An officer may need to review it.",
                )
            return redirect("borrower_dashboard")

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

    eligibility = None

    if application.status == "Pending":
        from .loan_eligibility import evaluate_loan_eligibility

        eligibility = evaluate_loan_eligibility(application)

    return render(
        request,
        "SysDataBase/loan_application_detail.html",
        {
            "application": application,
            "eligibility": eligibility,
        }
    )


@login_required
@require_POST

def loan_application_manual_review(request, application_id):

    # Only Admin and Loan Officer can perform manual reviews
    if (
        not request.user.is_authenticated
        or not request.user.roles
        or request.user.roles.roles_name not in ["Admin", "Loan Officer"]
    ):
        return HttpResponseForbidden(
            "You are not authorized to perform loan risk reviews."
        )

    # Manual review must be submitted using POST
    if request.method != "POST":
        return HttpResponseForbidden(
            "Manual risk review requires a POST request."
        )

    application = get_object_or_404(
        Loan_application,
        id=application_id
    )

    # Only pending applications without credit history need this review
    if (
        application.status != "Pending"
        or application.credit_score is not None
    ):
        messages.error(
            request,
            "This application is not eligible for manual risk review."
        )
        return redirect(
            "loan_application_detail",
            application_id=application.id
        )

    risk_category = request.POST.get("risk_category", "").strip()
    rate_input = request.POST.get("interest_rate", "").strip()
    review_notes = request.POST.get("review_notes", "").strip()

    valid_categories = [
        choice[0] for choice in Loan_application.RiskCategory.choices
    ]

    if risk_category not in valid_categories:
        messages.error(
            request,
            "Please select a valid risk category."
        )
        return redirect(
            "loan_application_detail",
            application_id=application.id
        )

    if not review_notes:
        messages.error(
            request,
            "Please provide notes explaining the risk decision."
        )
        return redirect(
            "loan_application_detail",
            application_id=application.id
        )

    from decimal import Decimal, InvalidOperation

    try:
        interest_rate = Decimal(rate_input)

        if not interest_rate.is_finite() or not (
            Decimal("0") < interest_rate <= Decimal("100")
        ):
            raise ValueError

    except (InvalidOperation, ValueError):
        messages.error(
            request,
            "Enter a valid annual interest rate greater than 0% and not above 100%."
        )
        return redirect(
            "loan_application_detail",
            application_id=application.id
        )

    # Save manual review and update automated evaluation together
    with transaction.atomic():

        application.risk_review_status = (
            Loan_application.RiskReviewStatus.COMPLETED
        )

        application.risk_category = risk_category
        application.manually_recommended_rate = interest_rate
        application.risk_review_notes = review_notes
        application.risk_review_by = request.user
        application.risk_reviewed_at = timezone.now()

        application.save()

        # Re-evaluate after manual risk review
        decision_result = evaluate_automatic_loan_decision(
            application
        )

        # Update eligibility classification
        application.eligibility_status = decision_result["decision"]
        application.save(update_fields=["eligibility_status"])

        # Record manual review history
        record_loan_application_history(
            application=application,
            action=LoanApplicationHistory.ActionType.RISK_REVIEWED,
            performed_by=request.user,
            previous_status="Pending Manual Review",
            new_status="Risk Review Completed",
            details=(
                f"Risk category: {risk_category}. "
                f"Recommended annual rate: {interest_rate}%. "
                f"Notes: {review_notes}. "
                f"Automated evaluation: "
                f"{decision_result['decision']}."
            )
        )

    messages.success(
        request,
        "Manual risk review completed successfully."
    )

    return redirect(
        "loan_application_detail",
        application_id=application.id
    )




@login_required
@require_POST
def loan_application_approve(request, application_id):
    from django.db import IntegrityError
    from .loan_approval_service import LoanApprovalError, approve_loan_application

    if (
        not request.user.is_staff
        or not request.user.roles
        or request.user.roles.roles_name not in ("Admin", "Loan Officer")
    ):
        return HttpResponseForbidden("You are not authorized to approve loans.")

    try:
        approve_loan_application(
            application_id=application_id,
            generate_agreement=generate_loan_agreement,
            approved_by=request.user,
            approval_source="manual",
        )
        messages.success(request, "Loan approved successfully.")
    except Loan_application.DoesNotExist:
        messages.error(request, "Loan application not found.")
    except LoanApprovalError as exc:
        messages.error(request, str(exc))
    except IntegrityError:
        messages.error(request, "A conflicting loan or agreement record exists.")

    return redirect("loan_application_detail", application_id=application_id)

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
    
    notify_loan_decision(application, approved=False)

    messages.success(request, "Loan application rejected successfully.")

    return redirect("loan_application_detail", application_id=application.id)

@login_required
@user_passes_test(lambda user: user.is_staff)
def savings_account_list(request):

    accounts = Savings_account.objects.select_related(
        "client_profile",
        "client_profile__users"
    ).order_by("-opened_at")

    search_query = request.GET.get("search", "").strip()

    if search_query:
        accounts = accounts.filter(
            Q(account_no__icontains=search_query) |
            Q(client_profile__first_name__icontains=search_query) |
            Q(client_profile__last_name__icontains=search_query) |
            Q(client_profile__users__username__icontains=search_query)
        )

    return render(
        request,
        "SysDataBase/savings_account_list.html",
        {
            "accounts": accounts,
            "search_query": search_query,
        }
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

    # Check account status before displaying the transaction form
    if account.status != Savings_account.AccountStatus.ACTIVE:
        messages.error(
            request,
            "Transactions are not allowed until the savings account is active."
        )
        return redirect("savings_account_list")

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

                    # Check status again before processing
                    if account.status != Savings_account.AccountStatus.ACTIVE:
                        messages.error(
                            request,
                            "This savings account is not active."
                        )
                        return redirect("savings_account_list")

                    if (
                        transaction_type == "Withdrawal"
                        and amount > account.current_balance
                    ):
                        messages.error(
                            request,
                            "Insufficient savings balance."
                        )
                    else:
                        savings_transaction = form.save(commit=False)
                        savings_transaction.savings_account = account
                        savings_transaction.reference_number = (
                            "TXN" + uuid.uuid4().hex[:12].upper()
                        )
                        savings_transaction.save()

                        if transaction_type in ["Deposit", "Interest"]:
                            account.current_balance += amount

                        elif transaction_type == "Withdrawal":
                            account.current_balance -= amount

                        account.save()

                        # Create Financial Ledger entries
                        if transaction_type == "Deposit":
                            Transaction_records.objects.create(
                                savings_transaction=savings_transaction,
                                debit_amount=amount,
                                credit_amount=Decimal("0.00"),
                                entry_type="Savings Deposit",
                                account_code="CASH"
                            )

                            Transaction_records.objects.create(
                                savings_transaction=savings_transaction,
                                debit_amount=Decimal("0.00"),
                                credit_amount=amount,
                                entry_type="Savings Deposit",
                                account_code="SAVINGS_LIABILITY"
                            )

                        elif transaction_type == "Withdrawal":
                            Transaction_records.objects.create(
                                savings_transaction=savings_transaction,
                                debit_amount=amount,
                                credit_amount=Decimal("0.00"),
                                entry_type="Savings Withdrawal",
                                account_code="SAVINGS_LIABILITY"
                            )

                            Transaction_records.objects.create(
                                savings_transaction=savings_transaction,
                                debit_amount=Decimal("0.00"),
                                credit_amount=amount,
                                entry_type="Savings Withdrawal",
                                account_code="CASH"
                            )

                        elif transaction_type == "Interest":
                            Transaction_records.objects.create(
                                savings_transaction=savings_transaction,
                                debit_amount=amount,
                                credit_amount=Decimal("0.00"),
                                entry_type="Savings Interest",
                                account_code="INTEREST_EXPENSE"
                            )

                            Transaction_records.objects.create(
                                savings_transaction=savings_transaction,
                                debit_amount=Decimal("0.00"),
                                credit_amount=amount,
                                entry_type="Savings Interest",
                                account_code="SAVINGS_LIABILITY"
                            )

                        messages.success(
                            request,
                            "Savings transaction and ledger entries recorded successfully."
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
        "savings_account__client_profile",
        "savings_account__client_profile__users"
    ).order_by("-transaction_date")

    search_query = request.GET.get("search", "").strip()
    transaction_type = request.GET.get("type", "").strip()

    if search_query:
        transactions = transactions.filter(
            Q(reference_number__icontains=search_query) |
            Q(savings_account__account_no__icontains=search_query) |
            Q(savings_account__client_profile__first_name__icontains=search_query) |
            Q(savings_account__client_profile__last_name__icontains=search_query) |
            Q(savings_account__client_profile__users__username__icontains=search_query)
        )

    if transaction_type:
        transactions = transactions.filter(
            transaction_type=transaction_type
        )

    return render(
        request,
        "SysDataBase/savings_transaction_list.html",
        {
            "transactions": transactions,
            "search_query": search_query,
            "selected_type": transaction_type,
        }
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

def add_months(original_date, months):
    month = original_date.month - 1 + months
    year = original_date.year + month // 12
    month = month % 12 + 1

    day = min(
        original_date.day,
        calendar.monthrange(year, month)[1]
    )

    return date(year, month, day)


def generate_amortization_schedule(loan):

    principal = loan.principal_amount
    term = loan.term_months

    if principal <= 0 or term <= 0:
        raise ValueError("Loan amount and term must be greater than zero.")

    monthly_rate = (
        loan.annual_interest_rate / Decimal("100") / Decimal("12")
    )

    if monthly_rate == 0:
        monthly_payment = principal / Decimal(term)
    else:
        growth = (Decimal("1") + monthly_rate) ** term

        monthly_payment = (
            principal * monthly_rate * growth
        ) / (growth - Decimal("1"))

    monthly_payment = monthly_payment.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    remaining_balance = principal
    schedules = []

    for installment in range(1, term + 1):

        interest = (
            remaining_balance * monthly_rate
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if installment == term:
            principal_due = remaining_balance
        else:
            principal_due = monthly_payment - interest

        total_due = principal_due + interest

        remaining_balance -= principal_due

        due_date = add_months(
            loan.disbursement_date,
            installment
        )

        schedules.append(
            Amortization_schedule(
                loans=loan,
                installment_no=installment,
                due_date=due_date,
                interest_due=interest,
                principal_due=principal_due,
                total_due=total_due,
                amount_paid=Decimal("0.00"),
                status="Pending"
            )
        )

    Amortization_schedule.objects.bulk_create(schedules)

def generate_loan_agreement(application, loan):
    agreement_number = "AGR" + uuid.uuid4().hex[:12].upper()

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25 * mm,
        leftMargin=25 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm
    )

    styles = getSampleStyleSheet()
    content = []

    client = application.client_profile
    borrower_name = f"{client.first_name} {client.last_name}"

    content.append(
        Paragraph("SAMPLE LOAN AGREEMENT", styles["Title"])
    )
    content.append(Spacer(1, 10))

    content.append(
        Paragraph(
            "<b>ACADEMIC DEMONSTRATION ONLY — DRAFT FOR REVIEW</b>",
            styles["Heading2"]
        )
    )
    content.append(Spacer(1, 15))

    content.append(
        Paragraph(f"Agreement Number: {agreement_number}", styles["Normal"])
    )
    content.append(Spacer(1, 10))

    loan_details = [
        ["Loan Information", "Details"],
        ["Borrower Name", borrower_name],
        ["Application Number", str(application.id)],
        ["Loan Amount", f"PHP {loan.principal_amount:,.2f}"],
        ["Annual Interest Rate", f"{loan.annual_interest_rate}%"],
        ["Loan Term", f"{loan.term_months} months"],
        ["Loan Purpose", application.purpose],
        ["Agreement Date", timezone.localdate().strftime("%B %d, %Y")],
    ]

    table = Table(loan_details, colWidths=[55 * mm, 95 * mm])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    content.append(table)
    content.append(Spacer(1, 25))

    content.append(
        Paragraph(
            "This is a system-generated draft for academic demonstration. "
            "The loan details must be reviewed before signing. "
            "A separate repayment schedule will be provided.",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 40))

    content.append(
        Paragraph("Borrower Signature: __________________________", styles["Normal"])
    )
    content.append(Spacer(1, 20))

    content.append(
        Paragraph("Authorized Officer: __________________________", styles["Normal"])
    )

    document.build(content)

    agreement = Loan_agreement(
        loan_application=application,
        agreement_number=agreement_number
    )

    agreement.agreement_document.save(
        f"{agreement_number}.pdf",
        ContentFile(buffer.getvalue()),
        save=False
    )

    agreement.save()

    return agreement

@login_required
@require_POST
def loan_disburse(request, loan_id):
    # LOAN DISBURSEMENT -> SAVINGS (single-credit atomic workflow)
    # An approved loan is not money in the borrower's account yet.
    # Credit savings only when staff explicitly disburses the loan.
    if (
        not request.user.is_staff
        or not request.user.roles
        or request.user.roles.roles_name not in ["Admin", "Loan Officer"]
    ):
        return HttpResponseForbidden("You are not authorized to disburse loans.")

    disbursement_date = parse_date(request.POST.get("disbursement_date", ""))
    if not disbursement_date or disbursement_date > timezone.localdate():
        messages.error(request, "Choose a valid disbursement date (not in the future).")
        return redirect("loan_list")

    # Show a proper 404 for unknown loan IDs.
    get_object_or_404(Loans, pk=loan_id)

    try:
        with transaction.atomic():
            # First obtain a write lock even on SQLite, where select_for_update
            # is ignored. Concurrent retries cannot both advance an Approved
            # loan. This write and everything below are committed together.
            claimed = Loans.objects.filter(
                pk=loan_id,
                status=Loans.LoanStatus.APPROVED,
                disbursement_date__isnull=True,
            ).update(updated_at=timezone.now())
            if claimed != 1:
                raise ValueError(
                    "This loan has already been disbursed or is not approved."
                )

            loan = Loans.objects.select_for_update().select_related(
                "loan_application__client_profile"
            ).get(pk=loan_id)

            if Amortization_schedule.objects.filter(loans=loan).exists():
                raise ValueError(
                    "An amortization schedule already exists. Please review this loan."
                )

            client = loan.loan_application.client_profile
            try:
                account = Savings_account.objects.select_for_update().get(
                    client_profile=client
                )
            except Savings_account.DoesNotExist:
                raise ValueError("The borrower has no savings account.")

            if account.status != Savings_account.AccountStatus.ACTIVE:
                raise ValueError(
                    "Activate the borrower's savings account before disbursement."
                )

            amount = loan.principal_amount
            if amount is None or amount <= Decimal("0.00"):
                raise ValueError("Loan principal must be greater than zero.")

            # Stable unique reference acts as an additional safeguard. Avoid
            # creating a second deposit for the same loan ID.
            reference = f"LOANDISB-{loan.pk}"
            if Savings_transaction.objects.filter(
                reference_number=reference
            ).exists():
                raise ValueError(
                    "A savings credit already exists for this loan."
                )

            # Represent loan proceeds as a Deposit in the existing transaction
            # model (no schema change required); the unique reference and ledger
            # entry_type distinguish it from a normal cash deposit.
            savings_transaction = Savings_transaction.objects.create(
                savings_account=account,
                transaction_type=Savings_transaction.TransactionType.DEPOSIT,
                reference_number=reference,
                amount=amount,
                status=Savings_transaction.TransactionStatus.APPROVED,
            )

            account.current_balance += amount
            account.save(update_fields=["current_balance", "updated_at"])

            # Internal credit: loan receivable increases (debit); the bank's
            # liability for the credited savings balance increases (credit).
            Transaction_records.objects.create(
                savings_transaction=savings_transaction,
                debit_amount=amount,
                credit_amount=Decimal("0.00"),
                entry_type="Loan Disbursement",
                account_code="LOAN_RECEIVABLE",
            )
            Transaction_records.objects.create(
                savings_transaction=savings_transaction,
                debit_amount=Decimal("0.00"),
                credit_amount=amount,
                entry_type="Loan Disbursement",
                account_code="SAVINGS_LIABILITY",
            )

            loan.disbursement_date = disbursement_date
            loan.status = Loans.LoanStatus.ACTIVE
            loan.save(update_fields=["disbursement_date", "status", "updated_at"])

            # Any failure while making the schedule rolls back the balance,
            # savings transaction, ledger and loan status together.
            generate_amortization_schedule(loan)

        messages.success(
            request,
            f"Loan disbursed! PHP {amount:,.2f} credited to the borrower's "
            f"savings account. Reference: {reference}"
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    except (ArithmeticError, InvalidOperation):
        messages.error(request, "Invalid loan details; disbursement was canceled.")
    except Exception:
        # A DB constraint error or another unexpected failure rolls back the
        # atomic transaction. The traceback is preserved in the server logs.
        import logging
        logging.getLogger(__name__).exception(
            "Loan disbursement failed for loan %s", loan_id
        )
        messages.error(
            request,
            "Disbursement failed; no loan credit was applied. Check server logs."
        )

    return redirect("loan_list")





@login_required
@require_POST
def loan_payment_create(request, schedule_id):

    if (
        not request.user.is_staff
        or not request.user.roles
        or request.user.roles.roles_name not in ["Admin", "Loan Officer"]
    ):
        return HttpResponseForbidden(
            "You are not authorized to record loan payments."
        )

    schedule = get_object_or_404(
        Amortization_schedule.objects.select_related("loans"),
        id=schedule_id
    )

    loan = schedule.loans

    if loan.status != Loans.LoanStatus.ACTIVE:
        messages.error(request, "Payments can only be recorded for active loans.")
        return redirect("loan_list")

    if schedule.status == Amortization_schedule.ScheduleStatus.PAID:
        messages.error(request, "This installment has already been fully paid.")
        return redirect("amortization_list", loan_id=loan.id)

    try:
        amount = Decimal(request.POST.get("amount", ""))

        if (
            not amount.is_finite()
            or amount <= 0
            or amount.as_tuple().exponent < -2
        ):
            raise ValueError

    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Please enter a valid payment amount.")
        return redirect("amortization_list", loan_id=loan.id)

    if amount > schedule.total_due - schedule.amount_paid:
        messages.error(request, "Payment exceeds the remaining installment amount.")
        return redirect("amortization_list", loan_id=loan.id)

    payment_method = request.POST.get("payment_method", "").strip()

    if payment_method not in ["Cash", "Bank Transfer", "Online Payment"]:
        messages.error(request, "Please select a valid payment method.")
        return redirect("amortization_list", loan_id=loan.id)

    with transaction.atomic():

        interest_already_paid = min(
            schedule.amount_paid,
            schedule.interest_due
        )

        remaining_interest = (
            schedule.interest_due - interest_already_paid
        )

        principal_portion = max(
            Decimal("0.00"),
            amount - remaining_interest
        )

        interest_portion = amount - principal_portion

        reference_number = "PAY" + uuid.uuid4().hex[:12].upper()

        payment = Loan_payments.objects.create(
            loans=loan,
            amortization_schedule=schedule,
            payment_date=timezone.localdate(),
            amount=amount,
            status=Loan_payments.PaymentStatus.COMPLETED,
            payment_method=payment_method,
            reference_number=reference_number
        )

        # Debit: Cash received
        Transaction_records.objects.create(
            loan_payment=payment,
            debit_amount=amount,
            credit_amount=Decimal("0.00"),
            entry_type="Loan Payment",
            account_code="CASH"
        )

        # Credit: Principal repayment
        if principal_portion > 0:
            Transaction_records.objects.create(
                loan_payment=payment,
                debit_amount=Decimal("0.00"),
                credit_amount=principal_portion,
                entry_type="Loan Principal Repayment",
                account_code="LOAN_RECEIVABLE"
            )

        # Credit: Interest earned
        if interest_portion > 0:
            Transaction_records.objects.create(
                loan_payment=payment,
                debit_amount=Decimal("0.00"),
                credit_amount=interest_portion,
                entry_type="Loan Interest Income",
                account_code="INTEREST_INCOME"
            )

        schedule.amount_paid += amount

        if schedule.amount_paid >= schedule.total_due:
            schedule.status = Amortization_schedule.ScheduleStatus.PAID
        else:
            schedule.status = Amortization_schedule.ScheduleStatus.PARTIAL

        schedule.save()

        loan.outstanding_balance = max(
            Decimal("0.00"),
            loan.outstanding_balance - principal_portion
        )

        if loan.outstanding_balance == Decimal("0.00"):
            loan.status = Loans.LoanStatus.PAID

        loan.save()

    messages.success(
        request,
        f"Payment and ledger entries recorded successfully. Reference: {reference_number}"
    )

    return redirect("amortization_list", loan_id=loan.id)

@login_required
def amortization_list(request, loan_id):

    loan = get_object_or_404(
        Loans.objects.select_related(
            "loan_application",
            "loan_application__client_profile"
        ),
        id=loan_id
    )

    role = request.user.roles.roles_name if request.user.roles else None

    if role in ["Admin", "Loan Officer", "Staff"] and request.user.is_staff:
        pass

    elif role == "Borrower":
        if loan.loan_application.client_profile.users != request.user:
            return HttpResponseForbidden(
                "You are not authorized to view this loan schedule."
            )

    else:
        return HttpResponseForbidden(
            "You are not authorized to view this schedule."
        )

    schedules = Amortization_schedule.objects.filter(
        loans=loan
    ).order_by("installment_no")

    return render(
        request,
        "SysDataBase/amortization_list.html",
        {
            "loan": loan,
            "schedules": schedules
        }
    )

@login_required
def loan_payment_list(request):

    role = (
        request.user.roles.roles_name
        if request.user.roles
        else None
    )

    payments = Loan_payments.objects.select_related(
        "loans",
        "loans__loan_application",
        "loans__loan_application__client_profile",
        "amortization_schedule"
    )

    if request.user.is_staff and role in ["Admin", "Loan Officer"]:
        pass

    elif role == "Borrower":
        payments = payments.filter(
            loans__loan_application__client_profile__users=request.user
        )

    else:
        return HttpResponseForbidden(
            "You are not authorized to view payment history."
        )

    payments = payments.order_by("-payment_date", "-created_at")

    return render(
        request,
        "SysDataBase/loan_payment_list.html",
        {"payments": payments}
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def transaction_record_list(request):

    records = Transaction_records.objects.select_related(
        "savings_transaction",
        "loan_payment"
    ).order_by("-entry_date", "-created_at")

    return render(
        request,
        "SysDataBase/transaction_record_list.html",
        {"records": records}
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def notification_list(request):

    User = get_user_model()

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        channel = request.POST.get("channel")
        message = request.POST.get("message", "").strip()

        recipient = get_object_or_404(
            User,
            id=user_id,
            is_active=True
        )

        if channel not in ["Email", "SMS"] or not message:
            messages.error(request, "Please provide valid notification details.")
        else:
            Notifications.objects.create(
                users=recipient,
                channel=channel,
                message=message,
                status=Notifications.NotificationStatus.PENDING
            )

            messages.success(
                request,
                "Notification created successfully."
            )

            return redirect("notification_list")

    notifications = Notifications.objects.select_related(
        "users"
    ).order_by("-created_at")

    users = User.objects.filter(is_active=True).order_by("username")

    return render(
        request,
        "SysDataBase/notification_list.html",
        {
            "notifications": notifications,
            "users": users
        }
    )

@login_required
def borrower_dashboard(request):

    role = request.user.roles.roles_name if request.user.roles else None

    if role != "Borrower":
        return HttpResponseForbidden(
            "This dashboard is for borrowers only."
        )

    try:
        client = request.user.client_profile
    except Client_profile.DoesNotExist:
        return HttpResponseForbidden(
            "No client profile found for this account."
        )

    savings_accounts = Savings_account.objects.filter(
        client_profile=client
    ).order_by("-opened_at")

    savings_transactions = Savings_transaction.objects.filter(
        savings_account__client_profile=client
    ).select_related(
        "savings_account"
    ).order_by("-transaction_date")[:10]

    applications = Loan_application.objects.filter(
        client_profile=client
    ).order_by("-application_date")

    loans = Loans.objects.filter(
        loan_application__client_profile=client
    ).select_related(
        "loan_application"
    ).order_by("-created_at")

    payments = Loan_payments.objects.filter(
        loans__loan_application__client_profile=client
    ).select_related(
        "loans",
        "amortization_schedule"
    ).order_by("-payment_date")[:10]

    notifications = Notifications.objects.filter(
        users=request.user
    ).order_by("-created_at")[:5]

    context = {
        "client": client,
        "savings_accounts": savings_accounts,
        "savings_transactions": savings_transactions,
        "applications": applications,
        "loans": loans,
        "payments": payments,
        "notifications": notifications,
        "transaction_form": BorrowerTransactionRequestForm()
    }

    return render(
        request,
        "SysDataBase/borrower_dashboard.html",
        context
    )


@login_required
def home_dashboard(request):

    role = (
        request.user.roles.roles_name
        if request.user.roles
        else None
    )

    # Redirect regular borrowers to their dashboard.
    if role == "Borrower" and not request.user.is_superuser:
        return redirect("borrower_dashboard")

    # Allow staff with management roles and Django superusers.
    if not (
        request.user.is_active
        and request.user.is_staff
        and (
            request.user.is_superuser
            or role in ["Admin", "Staff", "Loan Officer"]
        )
    ):
        return HttpResponseForbidden(
            "You are not authorized to access the Management Portal."
        )

    context = {
        "role": "Admin" if request.user.is_superuser else role,
        "total_clients": Client_profile.objects.count(),
        "total_applications": Loan_application.objects.count(),
        "pending_applications": Loan_application.objects.filter(
            status="Pending"
        ).count(),
        "total_loans": Loans.objects.count(),
        "total_savings_accounts": Savings_account.objects.count(),
        "total_payments": Loan_payments.objects.count(),
    }

    return render(
        request,
        "SysDataBase/home_dashboard.html",
        context
    )


def check_savings_ledger(savings_transaction):
    totals = Transaction_records.objects.filter(
        savings_transaction=savings_transaction
    ).aggregate(
        total_debit=Sum("debit_amount"),
        total_credit=Sum("credit_amount")
    )

    total_debit = totals["total_debit"] or Decimal("0.00")
    total_credit = totals["total_credit"] or Decimal("0.00")

    return total_debit == total_credit



@login_required
@require_POST
def borrower_transaction_request(request):
    role = (
        request.user.roles.roles_name
        if request.user.roles else None
    )

    if role != "Borrower":
        return HttpResponseForbidden("Borrowers only.")

    try:
        profile = request.user.client_profile
    except Client_profile.DoesNotExist:
        return HttpResponseForbidden("Client profile not found.")

    form = BorrowerTransactionRequestForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Invalid transaction details.")
        return redirect("borrower_dashboard")

    transaction_type = form.cleaned_data["transaction_type"]
    amount = form.cleaned_data["amount"]

    if transaction_type not in [
        Savings_transaction.TransactionType.DEPOSIT,
        Savings_transaction.TransactionType.WITHDRAWAL,
    ]:
        messages.error(request, "Invalid transaction type.")
        return redirect("borrower_dashboard")

    if (
        amount <= 0
        or not amount.is_finite()
        or amount.as_tuple().exponent < -2
    ):
        messages.error(request, "Enter a valid positive amount.")
        return redirect("borrower_dashboard")

    with transaction.atomic():
        account = get_object_or_404(
            Savings_account.objects.select_for_update(),
            client_profile=profile
        )

        if account.status != Savings_account.AccountStatus.ACTIVE:
            messages.error(
                request, "Your savings account is not active."
            )
            return redirect("borrower_dashboard")

        # Reserve funds against other pending withdrawal requests.
        if transaction_type == Savings_transaction.TransactionType.WITHDRAWAL:
            pending_total = (
                Savings_transaction.objects.filter(
                    savings_account=account,
                    status=Savings_transaction.TransactionStatus.PENDING,
                    transaction_type=(
                        Savings_transaction.TransactionType.WITHDRAWAL
                    )
                ).aggregate(total=Sum("amount"))["total"]
                or Decimal("0.00")
            )

            available = account.current_balance - pending_total

            if amount > available:
                messages.error(
                    request,
                    "Insufficient available balance."
                )
                return redirect("borrower_dashboard")

        Savings_transaction.objects.create(
            savings_account=account,
            transaction_type=transaction_type,
            amount=amount,
            reference_number=(
                "TXN" + uuid.uuid4().hex[:12].upper()
            ),
            status=Savings_transaction.TransactionStatus.PENDING
        )

    messages.success(
        request,
        "Transaction request submitted. Awaiting admin approval."
    )

    return redirect("borrower_dashboard")


def record_loan_application_history(
    application,
    action,
    performed_by=None,
    previous_status="",
    new_status="",
    details=""
):
    LoanApplicationHistory.objects.create(
        application=application,
        performed_by=performed_by,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        details=details
    )


## PROFILE ##

@login_required
def borrower_profile(request):
    role = request.user.roles.roles_name if request.user.roles else None

    if role != "Borrower":
        return HttpResponseForbidden(
            "This profile page is for borrowers only."
        )

    try:
        client = request.user.client_profile
    except Client_profile.DoesNotExist:
        return HttpResponseForbidden(
            "No client profile found for this account."
        )

    return render(
        request,
        "SysDataBase/borrower_profile.html",
        {"client": client}
    )

@login_required
def map_explorer(request):
    return render(request, "SysDataBase/map.html")


@login_required
def savings_transaction_review_list(request):
    role = (
        request.user.roles.roles_name
        if request.user.roles else None
    )

    if not (
            request.user.is_active
            and request.user.is_staff
            and (
                   request.user.is_superuser
                   or role == "Admin"
            )
        ):
            return HttpResponseForbidden("Admins only.")

    requests = (
        Savings_transaction.objects
        .filter(status=Savings_transaction.TransactionStatus.PENDING)
        .select_related(
            "savings_account",
            "savings_account__client_profile",
            "savings_account__client_profile__users"
        )
        .order_by("transaction_date")
    )

    return render(
        request,
        "SysDataBase/savings_transaction_review.html",
        {"requests": requests}
    )


@login_required
@require_POST
def savings_transaction_review(request, transaction_id):
    role = (
        request.user.roles.roles_name
        if request.user.roles else None
    )

    if not (
        request.user.is_active
        and request.user.is_staff
        and (
               request.user.is_superuser
               or role == "Admin"
        )
    ):
        return HttpResponseForbidden("Admins only.")

    decision = request.POST.get("decision")

    if decision not in ["approve", "reject"]:
        messages.error(request, "Invalid review decision.")
        return redirect("savings_transaction_review_list")

    with transaction.atomic():
        txn = get_object_or_404(
            Savings_transaction.objects.select_for_update(),
            pk=transaction_id
        )

        # Prevent duplicate approval or rejection.
        if txn.status != Savings_transaction.TransactionStatus.PENDING:
            messages.error(request, "Transaction already reviewed.")
            return redirect("savings_transaction_review_list")

        account = Savings_account.objects.select_for_update().get(
            pk=txn.savings_account_id
        )

        if decision == "approve":
            if account.status != Savings_account.AccountStatus.ACTIVE:
                messages.error(request, "Savings account is not active.")
                return redirect("savings_transaction_review_list")

            if txn.transaction_type == Savings_transaction.TransactionType.DEPOSIT:
                account.current_balance += txn.amount

                debit_code = "CASH"
                credit_code = "SAVINGS_LIABILITY"
                entry_type = "Savings Deposit"

            elif txn.transaction_type == Savings_transaction.TransactionType.WITHDRAWAL:
                if txn.amount > account.current_balance:
                    messages.error(
                        request,
                        "Insufficient balance. Cannot approve withdrawal."
                    )
                    return redirect("savings_transaction_review_list")

                account.current_balance -= txn.amount

                debit_code = "SAVINGS_LIABILITY"
                credit_code = "CASH"
                entry_type = "Savings Withdrawal"

            else:
                messages.error(request, "Invalid transaction type.")
                return redirect("savings_transaction_review_list")

            # Prevent processing records with existing ledger entries.
            if Transaction_records.objects.filter(
                savings_transaction=txn
            ).exists():
                messages.error(
                    request,
                    "This transaction already has ledger entries."
                )
                return redirect("savings_transaction_review_list")

            account.save(update_fields=["current_balance", "updated_at"])

            Transaction_records.objects.create(
                savings_transaction=txn,
                debit_amount=txn.amount,
                credit_amount=Decimal("0.00"),
                entry_type=entry_type,
                account_code=debit_code
            )

            Transaction_records.objects.create(
                savings_transaction=txn,
                debit_amount=Decimal("0.00"),
                credit_amount=txn.amount,
                entry_type=entry_type,
                account_code=credit_code
            )

            txn.status = Savings_transaction.TransactionStatus.APPROVED

        else:
            txn.status = Savings_transaction.TransactionStatus.REJECTED

        txn.save(update_fields=["status", "updated_at"])

        borrower = account.client_profile.users
        amount = txn.amount
        txn_type = txn.transaction_type
        reference = txn.reference_number
        decision_status = txn.status

        # Notify only after the database transaction commits.
        from .notifications import notify

        def send_decision_notification():
            notify(
                borrower,
                (
                    f"Your {txn_type.lower()} request of "
                    f"PHP {amount:,.2f} ({reference}) "
                    f"has been {decision_status.lower()}."
                ),
                subject=f"Savings Transaction {decision_status}"
            )

        transaction.on_commit(send_decision_notification)

    messages.success(
        request,
        f"Transaction {decision_status.lower()} successfully."
    )

    return redirect("savings_transaction_review_list")
