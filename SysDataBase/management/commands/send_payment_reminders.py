from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from SysDataBase.models import Amortization_schedule
from SysDataBase.notifications import notify


class Command(BaseCommand):
    help = "Send reminders for upcoming, due-today, and overdue loan installments."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=3,
                            help="Remind this many days before the due date.")

    def handle(self, *args, **options):
        today = timezone.localdate()
        remind_date = today + timedelta(days=options["days"])

        unpaid = Amortization_schedule.objects.exclude(
            status=Amortization_schedule.ScheduleStatus.PAID
        ).select_related(
            "loans__loan_application__client_profile__users"
        )

        sent = 0
        for s in unpaid.iterator():
            user = s.loans.loan_application.client_profile.users
            balance = s.total_due - s.amount_paid
            if balance <= 0:
                continue

            tag = f"Loan #{s.loans_id}, installment {s.installment_no}"
            amount = f"PHP {balance:,.2f}"
            due = s.due_date.strftime("%b %d, %Y")

            if s.due_date == remind_date:
                msg = f"Payment reminder: {tag} of {amount} is due on {due}."
                subject = "Payment Reminder"
            elif s.due_date == today:
                msg = f"Due today: {tag} of {amount} is due today ({due})."
                subject = "Payment Due Today"
            elif s.due_date < today:
                msg = f"Overdue: {tag} of {amount} was due on {due}. Please pay as soon as possible."
                subject = "Payment Overdue"
            else:
                continue

            if notify(user, msg, subject, dedupe=True):
                sent += 1

        self.stdout.write(self.style.SUCCESS(f"{sent} notification(s) created."))