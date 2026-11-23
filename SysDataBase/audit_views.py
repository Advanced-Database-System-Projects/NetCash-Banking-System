"""Read-only role-protected audit viewer and CSV export."""
import csv

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .audit_signals import write_audit
from .models import Audit_logs


def _can_view_audit(user):
    if not user.is_authenticated or not user.is_staff:
        return False
    role = user.roles.roles_name if user.roles_id else None
    return user.is_superuser or role == "Admin"


def _filtered_logs(request):
    q = request.GET.get("q", "").strip()[:100]
    start_text = request.GET.get("start", "").strip()
    end_text = request.GET.get("end", "").strip()
    start = parse_date(start_text) if start_text else None
    end = parse_date(end_text) if end_text else None
    if (start_text and not start) or (end_text and not end) or (start and end and start > end):
        return None
    logs = Audit_logs.objects.select_related("users").order_by("-action_timestamp", "-id")
    if q:
        logs = logs.filter(
            Q(users__username__icontains=q)
            | Q(action__icontains=q)
            | Q(entity_name__icontains=q)
            | Q(entity_id__icontains=q)
        )
    if start:
        logs = logs.filter(action_timestamp__date__gte=start)
    if end:
        logs = logs.filter(action_timestamp__date__lte=end)
    return logs


def _csv_safe(value):
    """Protect spreadsheet applications from CSV formula injection."""
    text = str(value) if value is not None else ""
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@login_required
def audit_log_list(request):
    if not _can_view_audit(request.user):
        return HttpResponseForbidden("Only authorized administrators can view audit logs.")
    logs = _filtered_logs(request)
    if logs is None:
        return HttpResponseBadRequest("Invalid date range; enter valid YYYY-MM-DD dates.")
    write_audit("VIEW", "Audit_logs", user_id=request.user.pk)
    page = Paginator(logs, 40).get_page(request.GET.get("page", 1))
    return render(request, "SysDataBase/audit_log_list.html", {
        "page_obj": page,
        "q": request.GET.get("q", "").strip()[:100],
        "start": request.GET.get("start", "").strip(),
        "end": request.GET.get("end", "").strip(),
    })


@login_required
def audit_log_export(request):
    if not _can_view_audit(request.user):
        return HttpResponseForbidden("Only authorized administrators can export audit logs.")
    logs = _filtered_logs(request)
    if logs is None:
        return HttpResponseBadRequest("Invalid date range; enter valid YYYY-MM-DD dates.")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="NetCash_Audit_Logs_{timezone.localdate():%Y%m%d}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(["Log ID", "Timestamp", "Username", "Action", "Entity", "Entity ID"])
    # Evaluate before logging the export, to avoid adding the export event to
    # the same CSV file. The app's expected classroom dataset is modest.
    for item in logs.iterator(chunk_size=500):
        local_when = timezone.localtime(item.action_timestamp)
        writer.writerow([
            item.id,
            local_when.strftime("%Y-%m-%d %H:%M:%S %z"),
            _csv_safe(item.users.username if item.users else "System/Unknown"),
            _csv_safe(item.action),
            _csv_safe(item.entity_name),
            _csv_safe(item.entity_id),
        ])
    write_audit("EXPORT", "Audit_logs", user_id=request.user.pk)
    return response
