from django.core.mail import send_mail
from django.utils import timezone

from .models import Notifications


def notify(user, message, subject="NetCash Notification", dedupe=False):
    """Save a notification, try to email it, and record Sent/Failed.

    dedupe=True skips it if this exact message was already sent to the user.
    """
    if dedupe and Notifications.objects.filter(users=user, message=message).exists():
        return None

    note = Notifications.objects.create(
        users=user,
        channel=Notifications.Channel.EMAIL,
        status=Notifications.NotificationStatus.PENDING,
        message=message,
    )

    try:
        if not user.email:
            raise ValueError("User has no email address.")
        send_mail(subject, message, None, [user.email])
        note.status = Notifications.NotificationStatus.SENT
        note.sent_at = timezone.now()
    except Exception:
        note.status = Notifications.NotificationStatus.FAILED

    note.save()
    return note


def notify_loan_decision(application, approved, interest_rate=None):
    user = application.client_profile.users
    if approved:
        message = (
            f"Good news! Your loan application of "
            f"PHP {application.amount_requested:,.2f} has been approved"
            + (f" at {interest_rate}% annual interest." if interest_rate else ".")
        )
        subject = "Loan Approved"
    else:
        message = (
            f"Your loan application of PHP {application.amount_requested:,.2f} "
            f"was not approved. Please contact us for details."
        )
        subject = "Loan Application Update"
    return notify(user, message, subject)