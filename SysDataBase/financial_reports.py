"""Read-only, role-protected financial reporting for BankingSys.

All money amounts are derived from existing ledger and loan records.
No changes to transactions, approvals, balances, or disbursements.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import (
    Amortization_schedule,
    Loan_payments,
    Loans,
    Transaction_records,
)

ZERO = Decimal("0.00")


def _money_aggregate(qs, column):
    return qs.aggregate(total=Sum(column))["total"] or ZERO


def _money(value):
    return f"PHP {value:,.2f}"


def _period(request):
    today = timezone.localdate()
    start_text = request.GET.get("start", "").strip()
    end_text = request.GET.get("end", "").strip()
    start = parse_date(start_text) if start_text else today.replace(day=1)
    end = parse_date(end_text) if end_text else today
    if not start or not end or start > end:
        return None
    return start, end


def _prepare_data(start, end):
    today = timezone.localdate()
    # Ledger entries belong to a period; credit/debit conventions are used
    # to compute actual recorded income and expense, not requested amounts.
    entries = Transaction_records.objects.filter(
        entry_date__date__gte=start, entry_date__date__lte=end
    )

    income_entries = entries.filter(account_code="INTEREST_INCOME")
    expense_entries = entries.filter(account_code="INTEREST_EXPENSE")
    interest_income = (
        _money_aggregate(income_entries, "credit_amount")
        - _money_aggregate(income_entries, "debit_amount")
    )
    savings_interest_expense = (
        _money_aggregate(expense_entries, "debit_amount")
        - _money_aggregate(expense_entries, "credit_amount")
    )
    net_interest_result = interest_income - savings_interest_expense

    ledger = list(
        entries.values("account_code")
        .annotate(
            total_debit=Sum("debit_amount"),
            total_credit=Sum("credit_amount"),
        )
        .order_by("account_code")
    )
    for row in ledger:
        row["total_debit"] = row["total_debit"] or ZERO
        row["total_credit"] = row["total_credit"] or ZERO
    total_debit = sum((x["total_debit"] for x in ledger), ZERO)
    total_credit = sum((x["total_credit"] for x in ledger), ZERO)

    disbursed_loans = Loans.objects.filter(
        disbursement_date__gte=start,
        disbursement_date__lte=end,
    )
    disbursement_total = _money_aggregate(disbursed_loans, "principal_amount")
    disbursement_count = disbursed_loans.count()

    payments = Loan_payments.objects.filter(
        payment_date__gte=start,
        payment_date__lte=end,
        status=Loan_payments.PaymentStatus.COMPLETED,
    )
    repayment_total = _money_aggregate(payments, "amount")
    payment_count = payments.count()

    # Current-state loan portfolio. Only loans already disbursed are counted
    # in the outstanding receivable; approved-but-not-released is excluded.
    open_loans = Loans.objects.filter(
        status__in=[Loans.LoanStatus.ACTIVE, Loans.LoanStatus.OVERDUE],
    )
    outstanding_principal = _money_aggregate(open_loans, "outstanding_balance")

    # Derive overdue by due date as well as explicit Overdue loan status;
    # status can remain Active when installments become past due.
    overdue_ids = set(
        Amortization_schedule.objects.filter(
            loans__status__in=[Loans.LoanStatus.ACTIVE, Loans.LoanStatus.OVERDUE],
            due_date__lt=today,
            amount_paid__lt=F("total_due"),
        ).values_list("loans_id", flat=True)
    )
    overdue_ids.update(
        Loans.objects.filter(status=Loans.LoanStatus.OVERDUE)
        .values_list("id", flat=True)
    )
    overdue_loans = list(
        Loans.objects.filter(pk__in=overdue_ids)
        .select_related("loan_application__client_profile")
        .order_by("id")
    )
    overdue_balance = sum((loan.outstanding_balance for loan in overdue_loans), ZERO)
    current_active_count = open_loans.exclude(id__in=overdue_ids).count()
    approved_count = Loans.objects.filter(status=Loans.LoanStatus.APPROVED).count()
    paid_count = Loans.objects.filter(status=Loans.LoanStatus.PAID).count()
    
    return {
        "start": start,
        "end": end,
        "generated_at": timezone.now(),
        "interest_income": interest_income,
        "savings_interest_expense": savings_interest_expense,
        "net_interest_result": net_interest_result,
        "disbursement_total": disbursement_total,
        "disbursement_count": disbursement_count,
        "repayment_total": repayment_total,
        "payment_count": payment_count,
        "outstanding_principal": outstanding_principal,
        "current_active_count": current_active_count,
        "overdue_count": len(overdue_loans),
        "overdue_balance": overdue_balance,
        "approved_count": approved_count,
        "paid_count": paid_count,
        "overdue_loans": overdue_loans,
        "ledger": ledger,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "ledger_balanced": total_debit == total_credit,
    }


def _pdf(data):
    # ReportLab is already used for loan agreements in this project.
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buff = BytesIO()
    doc = SimpleDocTemplate(
        buff, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph("BankingSys Financial Report", styles["Title"])]
    story.append(Paragraph(
        f"Reporting period: {data['start']:%b %d, %Y} to {data['end']:%b %d, %Y}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 10))

    def section(title, rows, col_widths=None):
        story.append(Paragraph(escape(title), styles["Heading2"]))
        grid = [[str(value) for value in row] for row in rows]
        table = Table(grid, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCFCE7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#166534")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAF9")]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#15803D")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(table)
        story.append(Spacer(1, 14))

    section("Income and Expense Summary (Recorded Interest)", [
        ["Metric", "Amount"],
        ["Loan interest income", _money(data["interest_income"])],
        ["Savings interest expense", _money(data["savings_interest_expense"])],
        ["Net interest result", _money(data["net_interest_result"])],
    ], [100 * mm, 65 * mm])
    story.append(Paragraph(
        "Important: This is a partial interest-based income statement. "
        "Operating expenses, fees, taxes and other unrecorded revenue are excluded. "
        "It is not a complete audited profit/loss statement.", styles["Normal"]
    ))
    story.append(Spacer(1, 12))

    section("Loan Movement (Selected Period)", [
        ["Metric", "Amount / Count"],
        ["Loans disbursed", f"{data['disbursement_count']} | {_money(data['disbursement_total'])}"],
        ["Completed repayments", f"{data['payment_count']} | {_money(data['repayment_total'])}"],
    ], [100 * mm, 65 * mm])

    section("Current Portfolio Snapshot (Today)", [
        ["Metric", "Value"],
        ["Approved, not disbursed", data["approved_count"]],
        ["Active, not overdue", data["current_active_count"]],
        ["Overdue loans", data["overdue_count"]],
        ["Fully paid loans", data["paid_count"]],
        ["Outstanding principal", _money(data["outstanding_principal"])],
        ["Overdue-loan principal", _money(data["overdue_balance"])],
    ], [100 * mm, 65 * mm])

    ledger_rows = [["Account", "Debit (PHP)", "Credit (PHP)"]]
    for item in data["ledger"]:
        ledger_rows.append([
            item["account_code"],
            f"{item['total_debit']:,.2f}",
            f"{item['total_credit']:,.2f}",
        ])
    ledger_rows.append([
        "TOTAL", f"{data['total_debit']:,.2f}", f"{data['total_credit']:,.2f}"
    ])
    section("General Ledger Summary (Selected Period)", ledger_rows,
            [65 * mm, 50 * mm, 50 * mm])
    story.append(Paragraph(
        "Ledger balance: " + ("Balanced" if data["ledger_balanced"] else "Difference detected"),
        styles["Normal"],
    ))
    story.append(Spacer(1, 12))

    overdue_rows = [["Loan", "Borrower", "Outstanding (PHP)"]]
    for loan in data["overdue_loans"]:
        borrower = str(loan.loan_application.client_profile)
        overdue_rows.append([
            f"#{loan.pk}", borrower[:35], f"{loan.outstanding_balance:,.2f}",
        ])
    if len(overdue_rows) == 1:
        overdue_rows.append(["-", "No overdue loans", "-"])
    if data["overdue_loans"]:
        section("Overdue Accounts (Current)", overdue_rows,
                [22 * mm, 93 * mm, 50 * mm])
    doc.build(story)
    return buff.getvalue()


@login_required
def financial_report(request):
    role = getattr(getattr(request.user, "roles", None), "roles_name", None)
    if not (
        request.user.is_active
        and request.user.is_staff
        and (request.user.is_superuser or role in ("Admin", "Staff", "Loan Officer"))
    ):
        return HttpResponseForbidden("Not authorized to view financial reports.")

    dates = _period(request)
    if dates is None:
        return HttpResponseBadRequest("Enter valid reporting dates. Start must not exceed end.")
    data = _prepare_data(*dates)

    if request.GET.get("download") == "pdf":
        response = HttpResponse(_pdf(data), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="BankingSys_Financial_Report_{data["start"]}_{data["end"]}.pdf"'
        )
        response["Cache-Control"] = "private, no-store"
        return response

    response = render(request, "SysDataBase/financial_report.html", data)
    response["Cache-Control"] = "private, no-store"
    return response
