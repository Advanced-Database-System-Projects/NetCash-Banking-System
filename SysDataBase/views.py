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

            # Record application submission
            record_loan_application_history(
                application=application,
                action=LoanApplicationHistory.ActionType.SUBMITTED,
                performed_by=request.user,
                previous_status="",
                new_status=application.status,
                details="Borrower submitted a new loan application."
            )

            messages.success(
                request,
                "Your loan application was submitted successfully."
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
        not request.user.roles
        or request.user.roles.roles_name not in ["Admin", "Loan Officer"]
    ):
        return HttpResponseForbidden(
            "You are not authorized to perform loan risk reviews."
        )

    application = get_object_or_404(
        Loan_application,
        id=application_id
    )

    # Only pending applications without credit history need this review
    if application.status != "Pending" or application.credit_score is not None:
        messages.error(request, "This application is not eligible for manual risk review.")
        return redirect("loan_application_detail", application_id=application.id)

    risk_category = request.POST.get("risk_category", "").strip()
    rate_input = request.POST.get("interest_rate", "").strip()
    review_notes = request.POST.get("review_notes", "").strip()

    valid_categories = [
        choice[0] for choice in Loan_application.RiskCategory.choices
    ]

    if risk_category not in valid_categories:
        messages.error(request, "Please select a valid risk category.")
        return redirect("loan_application_detail", application_id=application.id)

    if not review_notes:
        messages.error(request, "Please provide notes explaining the risk decision.")
        return redirect("loan_application_detail", application_id=application.id)

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
        return redirect("loan_application_detail", application_id=application.id)

    # Save the manual review and its history together
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

        record_loan_application_history(
            application=application,
            action=LoanApplicationHistory.ActionType.RISK_REVIEWED,
            performed_by=request.user,
            previous_status="Pending Manual Review",
            new_status="Risk Review Completed",
            details=(
                f"Risk category: {risk_category}. "
                f"Recommended annual rate: {interest_rate}%. "
                f"Notes: {review_notes}"
            )
        )

    messages.success(
        request,
        "Manual risk review completed successfully."
    )

    return redirect("loan_application_detail", application_id=application.id)


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

    from .loan_eligibility import evaluate_loan_eligibility

    eligibility = evaluate_loan_eligibility(application)

    if not eligibility["eligible"]:
        messages.error(
            request,
            "This application does not meet the eligibility requirements."
        )
        return redirect("loan_application_detail", application_id=application.id)

    interest_rate = eligibility["recommended_interest_rate"]

    if interest_rate is None:
        messages.error(
            request,
            "Manual risk review is required before this loan can be approved."
        )
        return redirect("loan_application_detail", application_id=application.id)

    if Loans.objects.filter(loan_application=application).exists():
        messages.error(request, "A loan record already exists for this application.")
        return redirect("loan_application_detail", application_id=application.id)

    if Loan_agreement.objects.filter(loan_application=application).exists():
        messages.error(request, "A loan agreement already exists for this application.")
        return redirect("loan_application_detail", application_id=application.id)

    with transaction.atomic():

        loan = Loans.objects.create(
            loan_application=application,
            term_months=application.requested_term_months,
            annual_interest_rate=interest_rate,
            principal_amount=application.amount_requested,
            outstanding_balance=application.amount_requested,
            status="Approved"
        )

        # Preserve automatic loan agreement PDF generation
        generate_loan_agreement(application, loan)

        application.status = "Approved"
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save()

    messages.success(
        request,
        f"Loan approved with a recommended annual interest rate of {interest_rate}%."
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

    if not request.user.is_staff or not request.user.roles or request.user.roles.roles_name not in ["Admin", "Loan Officer"]:
        return HttpResponseForbidden("You are not authorized to disburse loans.")

    loan = get_object_or_404(Loans, id=loan_id)

    if loan.status != Loans.LoanStatus.APPROVED:
        messages.error(request, "Only approved loans can be disbursed.")
        return redirect("loan_list")

    disbursement_date = parse_date(
        request.POST.get("disbursement_date", "")
    )

    if not disbursement_date:
        messages.error(request, "Please enter a valid disbursement date.")
        return redirect("loan_list")

    if disbursement_date > timezone.localdate():
        messages.error(request, "The disbursement date cannot be in the future.")
        return redirect("loan_list")

    if Amortization_schedule.objects.filter(loans=loan).exists():
        messages.error(request, "An amortization schedule already exists.")
        return redirect("loan_list")

    try:
        with transaction.atomic():

            loan.disbursement_date = disbursement_date
            loan.status = Loans.LoanStatus.ACTIVE
            loan.save()

            generate_amortization_schedule(loan)

        messages.success(
            request,
            "Loan successfully disbursed and amortization schedule generated."
        )

    except (ValueError, ArithmeticError):
        messages.error(
            request,
            "Unable to generate the amortization schedule. Please check the loan details."
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

    role = request.user.roles.roles_name if request.user.roles else None

    if role == "Borrower":
        return redirect("borrower_dashboard")

    if (
        not request.user.is_staff
        or role not in ["Admin", "Staff", "Loan Officer"]
    ):
        return HttpResponseForbidden(
            "You are not authorized to access the Management Portal."
        )

    context = {
        "role": role,
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

    # Only borrowers can use this feature
    role = request.user.roles.roles_name if request.user.roles else None

    if role != "Borrower":
        return HttpResponseForbidden("Borrowers only.")

    try:
        profile = request.user.client_profile
    except Client_profile.DoesNotExist:
        return HttpResponseForbidden("Client profile not found.")

    account = get_object_or_404(
        Savings_account,
        client_profile=profile
    )

    if account.status != Savings_account.AccountStatus.ACTIVE:
        messages.error(
            request,
            "Your savings account is not active."
        )
        return redirect("borrower_dashboard")

    form = BorrowerTransactionRequestForm(request.POST)

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)

        return redirect("borrower_dashboard")

    transaction_type = form.cleaned_data["transaction_type"]
    amount = form.cleaned_data["amount"]

    with transaction.atomic():

        # Lock the savings account while processing
        account = Savings_account.objects.select_for_update().get(
            id=account.id
        )

        if account.status != Savings_account.AccountStatus.ACTIVE:
            messages.error(request, "Your account is not active.")
            return redirect("borrower_dashboard")

        # Check withdrawal balance before processing
        if (
            transaction_type == Savings_transaction.TransactionType.WITHDRAWAL
            and amount > account.current_balance
        ):
            messages.error(
                request,
                "Insufficient savings balance."
            )
            return redirect("borrower_dashboard")

        # Create a pending transaction
        savings_transaction = Savings_transaction.objects.create(
            savings_account=account,
            transaction_type=transaction_type,
            reference_number="TXN" + uuid.uuid4().hex[:12].upper(),
            amount=amount,
            status=Savings_transaction.TransactionStatus.PENDING
        )

        # Simulate deposit or withdrawal processing
        gateway_result = simulate_payment(amount)

        if gateway_result["status"] != "SUCCESS":
            savings_transaction.status = (
                Savings_transaction.TransactionStatus.FAILED
            )
            savings_transaction.save()

            messages.error(
                request,
                "Transaction failed. Your balance was not changed."
            )
            return redirect("borrower_dashboard")

        # Update balance only after successful simulated processing
        if transaction_type == Savings_transaction.TransactionType.DEPOSIT:
            account.current_balance += amount
            entry_type = "Savings Deposit"
            debit_account = "CASH"
            credit_account = "SAVINGS_LIABILITY"

        else:
            account.current_balance -= amount
            entry_type = "Savings Withdrawal"
            debit_account = "SAVINGS_LIABILITY"
            credit_account = "CASH"

        account.save()

        # Mark transaction as approved
        savings_transaction.status = (
            Savings_transaction.TransactionStatus.APPROVED
        )
        savings_transaction.save()

        # Create balanced accounting entries
        Transaction_records.objects.create(
            savings_transaction=savings_transaction,
            debit_amount=amount,
            credit_amount=Decimal("0.00"),
            entry_type=entry_type,
            account_code=debit_account
        )

        Transaction_records.objects.create(
            savings_transaction=savings_transaction,
            debit_amount=Decimal("0.00"),
            credit_amount=amount,
            entry_type=entry_type,
            account_code=credit_account
        )

    messages.success(
        request,
        "Your transaction was successfully processed!"
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
