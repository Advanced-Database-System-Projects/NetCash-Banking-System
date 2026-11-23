"""Add a one-active-loan application rule to BankingSys borrower submissions.

Usage (Windows CMD, BankingSys root): python install_one_active_loan_rule.py
Only edits SysDataBase/views.py; creates a dated backup beforehand.
Requires the earlier automatic-loan-approval installer to have been applied.
"""
from pathlib import Path
from datetime import datetime
import ast
import shutil
import sys

START_MARKER = 'def loan_application_create(request):'
RULE_MARKER = '# RULE: ONE ACTIVE LOAN PER BORROWER'

RULE_HELPER = '''\
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


'''

PRE_FORM_GUARD = '''\
    # Check the rule even when borrower opens the application form directly.
    block_reason = get_loan_application_block_reason(client)
    if block_reason:
        messages.warning(request, block_reason)
        return redirect("borrower_dashboard")

'''

IN_TRANSACTION_REPLACEMENT = '''\
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
                application.save()'''


def main():
    root = Path.cwd()
    views_file = root / "SysDataBase" / "views.py"
    if not (root / "manage.py").is_file() or not views_file.is_file():
        print("ERROR: Run inside BankingSys, next to manage.py.")
        return 1

    source = views_file.read_text(encoding="utf-8-sig")
    if RULE_MARKER in source:
        print("Already installed. Nothing changed.")
        return 0
    if source.count(START_MARKER) != 1:
        print("ERROR: Cannot uniquely identify loan_application_create(). No changes made.")
        return 1

    # Find the borrower view and its preceding @login_required decorator.
    func_start = source.index(START_MARKER)
    decorator_pos = source.rfind('@login_required', 0, func_start)
    if decorator_pos < 0 or source[decorator_pos:func_start].strip() != '@login_required':
        print("ERROR: Borrower view decorator differs from expected. No changes made.")
        return 1
    next_decorator = source.find('\n@login_required', func_start + len(START_MARKER))
    if next_decorator < 0:
        print("ERROR: Could not identify end of borrower view. No changes made.")
        return 1

    borrower_view = source[decorator_pos:next_decorator]
    pre_form_anchor = '    if request.method == "POST":'
    transaction_anchor = '            with transaction.atomic():\n                application.save()'
    if borrower_view.count(pre_form_anchor) != 1 or borrower_view.count(transaction_anchor) != 1:
        print(
            "ERROR: Borrower submission function differs from the earlier "
            "automation installer. No changes made. Send the current "
            "loan_application_create() function for a safe adaptation."
        )
        return 1

    borrower_view = borrower_view.replace(pre_form_anchor, PRE_FORM_GUARD + pre_form_anchor, 1)
    borrower_view = borrower_view.replace(transaction_anchor, IN_TRANSACTION_REPLACEMENT, 1)
    new_source = (
        source[:decorator_pos]
        + RULE_HELPER
        + borrower_view
        + source[next_decorator:]
    )
    try:
        ast.parse(new_source, filename=str(views_file))
    except SyntaxError as exc:
        print(f"ERROR: Syntax check failed: {exc}. No files changed.")
        return 1

    backup_dir = root / ".git" / "loan_rule_backups" if (root / ".git").is_dir() else root / "loan_rule_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"views_{datetime.now():%Y%m%d_%H%M%S_%f}.py"
    shutil.copy2(views_file, dest)
    views_file.write_text(new_source, encoding="utf-8", newline="\n")
    print("Installed: ONE ACTIVE LOAN rule in SysDataBase/views.py")
    print("Backup:", dest)
    print("Blocked: pending applications and loans not fully paid.")
    print("Allowed again: rejected application or fully Paid loan with zero balance.")
    print("Next: python manage.py check")
    return 0

if __name__ == "__main__":
    sys.exit(main())
