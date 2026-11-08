
from django.core.management.base import BaseCommand
from django.utils import timezone

from SysDataBase.models import Savings_account
from SysDataBase.interest_service import credit_monthly_interest


class Command(BaseCommand):
    help = "Credit monthly interest to all active savings accounts."

    def handle(self, *args, **options):

        now = timezone.localtime()

        year = now.year
        month = now.month

        accounts = Savings_account.objects.filter(
            status=Savings_account.AccountStatus.ACTIVE
        )

        processed = 0
        credited = 0

        self.stdout.write(
            f"Processing savings interest for {year}-{month:02d}"
        )

        for account in accounts.iterator():

            result = credit_monthly_interest(
                account.id,
                year=year,
                month=month
            )

            processed += 1

            if result["success"]:
                credited += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"{account.account_no}: "
                        f"Interest credited: "
                        f"PHP {result['interest']}"
                    )
                )
            else:
                self.stdout.write(
                    f"{account.account_no}: {result['message']}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Accounts checked: {processed}. "
                f"Interest credits: {credited}."
            )
        )
