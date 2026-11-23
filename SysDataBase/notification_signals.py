"""In-app notifications for real BankingSys loan events.

These receivers run inside the same database transaction as the corresponding
model save. If the loan transaction rolls back, its notification rolls back.
No email or SMS is sent by this module.
"""
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Loan_application, Loans, Loan_payments, Notifications


def _notify(user, message):
    """Make a dashboard notification, avoiding repeat identical messages."""
    if user is None:
        return
    Notifications.objects.get_or_create(
        users=user,
        channel=Notifications.Channel.IN_APP,
        message=message,
        defaults={
            'status': Notifications.NotificationStatus.SENT,
            'sent_at': timezone.now(),
        },
    )


@receiver(pre_save, sender=Loan_application, dispatch_uid='bankingsys_application_before_save')
def _application_before_save(sender, instance, **kwargs):
    instance._notice_previous_status = None
    if instance.pk:
        instance._notice_previous_status = (
            Loan_application.objects.filter(pk=instance.pk)
            .values_list('status', flat=True).first()
        )


@receiver(post_save, sender=Loan_application, dispatch_uid='bankingsys_application_after_save')
def _application_after_save(sender, instance, created, update_fields=None, **kwargs):
    # Do not interpret an eligibility-only save as a status transition.
    if not created and update_fields is not None and 'status' not in update_fields:
        return
    user = instance.client_profile.users
    if created:
        _notify(user, f'Loan application #{instance.pk} was submitted successfully.')
    elif instance._notice_previous_status != instance.status:
        if instance.status == Loan_application.ApplicationStatus.APPROVED:
            _notify(user, (
                f'Loan application #{instance.pk} was approved. '
                'Funds will appear in savings only after disbursement.'
            ))
        elif instance.status == Loan_application.ApplicationStatus.REJECTED:
            _notify(user, (
                f'Loan application #{instance.pk} was rejected. '
                'Please contact an authorized officer if you need clarification.'
            ))


@receiver(pre_save, sender=Loans, dispatch_uid='bankingsys_loan_before_save')
def _loan_before_save(sender, instance, **kwargs):
    instance._notice_previous_status = None
    if instance.pk:
        instance._notice_previous_status = (
            Loans.objects.filter(pk=instance.pk)
            .values_list('status', flat=True).first()
        )


@receiver(post_save, sender=Loans, dispatch_uid='bankingsys_loan_after_save')
def _loan_after_save(sender, instance, created, update_fields=None, **kwargs):
    if created or (
        update_fields is not None and 'status' not in update_fields
    ) or instance._notice_previous_status == instance.status:
        return
    user = instance.loan_application.client_profile.users
    if instance.status == Loans.LoanStatus.ACTIVE:
        _notify(user, (
            f'Loan #{instance.pk} was disbursed. '
            f'PHP {instance.principal_amount:,.2f} was credited to your savings.'
        ))
    elif instance.status == Loans.LoanStatus.PAID:
        _notify(user, (
            f'Loan #{instance.pk} is now fully paid. '
            'You may apply again if there are no other open obligations.'
        ))


@receiver(post_save, sender=Loan_payments, dispatch_uid='bankingsys_payment_after_save')
def _payment_after_save(sender, instance, created, **kwargs):
    if not created or instance.status != Loan_payments.PaymentStatus.COMPLETED:
        return
    user = instance.loans.loan_application.client_profile.users
    _notify(user, (
        f'Loan payment {instance.reference_number} was recorded for '
        f'PHP {instance.amount:,.2f} on loan #{instance.loans_id}.'
    ))
