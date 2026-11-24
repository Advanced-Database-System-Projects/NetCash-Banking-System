"""Private, on-demand loan agreement PDF downloads for NetCash.

The existing loan approval workflow creates a single Loan_agreement record and
tries to save its PDF. This endpoint downloads that saved PDF when available.
For unsigned academic drafts whose file was lost on ephemeral hosting, it
regenerates a viewable copy in memory without creating another database record.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Loan_agreement, Loans


def _regenerate_unsigned_draft(agreement, loan):
    """Rebuild a *draft*, not a historical/signed original, without saving data."""
    application = loan.loan_application
    client = application.client_profile
    styles = getSampleStyleSheet()
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=25 * mm, leftMargin=25 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )

    borrower_name = escape(f"{client.first_name} {client.last_name}")
    safe_purpose = escape(str(application.purpose or ""))
    # Use the historical record creation date, not today's date.
    agreement_date = timezone.localtime(agreement.created_at).strftime("%B %d, %Y")

    content = [
        Paragraph("LOAN AGREEMENT", styles["Title"]),
        Spacer(1, 10),
        Paragraph(
            "<b>ACADEMIC DEMONSTRATION ONLY - DRAFT FOR REVIEW</b>",
            styles["Heading2"],
        ),
        Spacer(1, 7),
        Paragraph(
            "REGENERATED UNSIGNED DRAFT - NOT THE ORIGINAL SAVED FILE",
            styles["Normal"],
        ),
        Spacer(1, 15),
        Paragraph(
            f"Agreement Number: {escape(agreement.agreement_number)}",
            styles["Normal"],
        ),
        Spacer(1, 10),
    ]

    rows = [
        ["Loan Information", "Details"],
        ["Borrower Name", Paragraph(borrower_name, styles["Normal"])],
        ["Application Number", str(application.pk)],
        ["Loan Amount", f"PHP {loan.principal_amount:,.2f}"],
        ["Annual Interest Rate", f"{loan.annual_interest_rate}%"],
        ["Loan Term", f"{loan.term_months} months"],
        ["Loan Purpose", Paragraph(safe_purpose, styles["Normal"])],
        ["Agreement Date", agreement_date],
    ]

    table = Table(rows, colWidths=[55 * mm, 95 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    content.extend([
        table,
        Spacer(1, 25),
        Paragraph(
            "This is a system-generated draft for academic demonstration. "
            "The loan details must be reviewed before signing. "
            "A separate repayment schedule will be provided.",
            styles["Normal"],
        ),
        Spacer(1, 40),
        Paragraph("Borrower Signature: __________________________", styles["Normal"]),
        Spacer(1, 20),
        Paragraph("Authorized Officer: __________________________", styles["Normal"]),
    ])

    doc.build(content)
    buf.seek(0)
    return buf


@login_required
@require_GET
@never_cache
def download_loan_agreement(request, loan_id):
    """Admin-only PDF download. Never exposes a public media URL."""
    user = request.user
    role = getattr(getattr(user, "roles", None), "roles_name", None)
    if not (
        user.is_active
        and user.is_staff
        and (user.is_superuser or role == "Admin")
    ):
        return HttpResponseForbidden("Admins only.")

    loan = get_object_or_404(
        Loans.objects.select_related("loan_application__client_profile"),
        pk=loan_id,
    )
    agreement = get_object_or_404(
        Loan_agreement,
        loan_application=loan.loan_application,
    )

    filename = f"Loan_Agreement_{loan.pk}_{agreement.agreement_number}.pdf"
    original = None
    if agreement.agreement_document:
        try:
            # Unlike .url, this uses the storage backend and checks permissions
            # on the request before returning the private file.
            original = agreement.agreement_document.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            original = None

    # Never reconstruct a signed agreement: a signature/original is evidence.
    if agreement.signed_at is not None:
        if original is None:
            raise Http404("Signed agreement is unavailable. Restore the original PDF.")
        response = FileResponse(
            original, as_attachment=True,
            filename=filename, content_type="application/pdf",
        )
    else:
        # Older unsigned stored PDFs may still have the SAMPLE title. Return
        # a clearly labeled fresh unsigned copy; preserve the stored original.
        if original is not None:
            original.close()
        regenerated = _regenerate_unsigned_draft(agreement, loan)
        response = FileResponse(
            regenerated, as_attachment=True,
            filename=filename, content_type="application/pdf",
        )
        response["X-Loan-Agreement-Copy"] = "regenerated-unsigned-draft"

    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
