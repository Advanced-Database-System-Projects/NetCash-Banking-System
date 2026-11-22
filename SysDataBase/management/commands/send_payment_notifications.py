
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from SysDataBase.models import (
    Amortization_schedule,
    Notifications,
)


class Command(BaseCommand):
    help = "Generate automatic loan payment notifications."

    def handle(self, *args, **options):
        today = timezone.localdate()
        reminder_date = today + timedelta(days=3)

        schedules = Amortization_schedule.objects.select_related(
            "loans",
            "loans__loan_application",
            "loans__loan_application__client_profile",
            "loans__loan_application__client_profile__users",
        ).exclude(
            status=Amortization_schedule.ScheduleStatus.PAID
        )

        created_count = 0

        for schedule in schedules:
            if schedule.amount_paid >= schedule.total_due:
                continue

            borrower = schedule.loans.loan_application.client_profile.users

            remaining = schedule.total_due - schedule.amount_paid

            if schedule.due_date == reminder_date:
                notification_type = (
                    Notifications.NotificationType.PAYMENT_REMINDER
                )
                title = "Upcoming Loan Payment"
                message = (
                    f"Your installment #{schedule.installment_no} "
                    f"is due in 3 days. Remaining amount: "
                    f"₱{remaining:,.2f}."
                )
                key_type = "reminder_3_days"

            elif schedule.due_date == today:
                notification_type = (
                    Notifications.NotificationType.PAYMENT_DUE
                )
                title = "Loan Payment Due Today"
                message = (
                    f"Your installment #{schedule.installment_no} "
                    f"is due today. Remaining amount: "
                    f"₱{remaining:,.2f}."
                )
                key_type = "due_today"

            elif schedule.due_date < today:
                notification_type = (
                    Notifications.NotificationType.PAYMENT_OVERDUE
                )
                title = "Overdue Loan Payment"
                message = (
                    f"Your installment #{schedule.installment_no} "
                    f"is overdue. Remaining amount: "
                    f"₱{remaining:,.2f}."
                )
                key_type = "overdue"

                if schedule.status != (
                    Amortization_schedule.ScheduleStatus.OVERDUE
                ):
                    schedule.status = (
                        Amortization_schedule.ScheduleStatus.OVERDUE
                    )
                    schedule.save(update_fields=["status"])

            else:
                continue

            key = f"schedule:{schedule.id}:{key_type}"

            _, created = Notifications.objects.get_or_create(
                deduplication_key=key,
                defaults={
                    "users": borrower,
                    "notification_type": notification_type,
                    "channel": Notifications.Channel.IN_APP,
                    "status": Notifications.NotificationStatus.SENT,
                    "title": title,
                    "message": message,
                    "sent_at": timezone.now(),
                },
            )

            if created:
                created_count += 1

            # Notify staff/admin about overdue installments.
            if key_type == "overdue":
                staff_users = (
                    borrower.__class__.objects.filter(
                        is_staff=True,
                        roles__roles_name__in=[
                            "Admin",
                            "Loan Officer",
                            "Staff",
                        ],
                    ).distinct()
                )

                for staff_user in staff_users:
                    staff_key = (
                        f"schedule:{schedule.id}:overdue:staff:"
                        f"{staff_user.id}"
                    )

                    _, staff_created = Notifications.objects.get_or_create(
                        deduplication_key=staff_key,
                        defaults={
                            "users": staff_user,
                            "notification_type": notification_type,
                            "channel": Notifications.Channel.IN_APP,
                            "status": Notifications.NotificationStatus.SENT,
                            "title": "Borrower Payment Overdue",
                            "message": (
                                f"Installment #{schedule.installment_no} "
                                f"for Loan #{schedule.loans_id} is overdue. "
                                f"Remaining amount: ₱{remaining:,.2f}."
                            ),
                            "sent_at": timezone.now(),
                        },
                    )

                    if staff_created:
                        created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Payment notification check completed. "
                f"{created_count} new notifications created."
            )
        )
