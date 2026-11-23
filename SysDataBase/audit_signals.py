"""Audit important BankingSys database changes without storing sensitive field values.

Post-save/delete receivers are registered once in AppConfig.ready(). The audit row
is written in the same transaction as the corresponding database change. Bulk
QuerySet.update()/bulk_create() and raw SQL do not emit Django model signals.
"""
from contextvars import ContextVar

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_delete, post_save

from .models import (
    Audit_logs,
    Amortization_schedule,
    Client_profile,
    Loan_agreement,
    Loan_application,
    Loan_payments,
    Loans,
    Notifications,
    Roles,
    Savings_account,
    Savings_transaction,
    Transaction_records,
    User,
)

# Isolated by request/context, unlike a process-global "current user".
_actor_id = ContextVar("bankingsys_audit_actor", default=None)


def start_actor(user_id):
    return _actor_id.set(user_id)


def stop_actor(token):
    _actor_id.reset(token)


def write_audit(action, entity_name, entity_id="", user_id=None):
    # An explicit user_id takes priority, e.g. successful login.
    if user_id is None:
        user_id = _actor_id.get()
    return Audit_logs.objects.create(
        users_id=user_id,
        action=str(action)[:100],
        entity_name=str(entity_name)[:50],
        entity_id=str(entity_id)[:50] if entity_id is not None else "",
    )


def _record_save(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    write_audit("CREATE" if created else "UPDATE", sender.__name__, instance.pk)


def _record_delete(sender, instance, **kwargs):
    write_audit("DELETE", sender.__name__, instance.pk)


def _record_login(sender, request, user, **kwargs):
    write_audit("LOGIN", "User", user.pk, user_id=user.pk)


def _record_logout(sender, request, user, **kwargs):
    if user is not None:
        write_audit("LOGOUT", "User", user.pk, user_id=user.pk)


AUDITED_MODELS = (
    User, Roles, Client_profile, Savings_account, Savings_transaction,
    Loan_application, Loan_agreement, Loans, Amortization_schedule,
    Loan_payments, Transaction_records, Notifications,
)


def install_receivers():
    for model in AUDITED_MODELS:
        post_save.connect(
            _record_save,
            sender=model,
            weak=False,
            dispatch_uid=f"bankingsys_audit_save_{model._meta.label_lower}",
        )
        post_delete.connect(
            _record_delete,
            sender=model,
            weak=False,
            dispatch_uid=f"bankingsys_audit_delete_{model._meta.label_lower}",
        )
    user_logged_in.connect(
        _record_login,
        weak=False,
        dispatch_uid="bankingsys_audit_auth_login",
    )
    user_logged_out.connect(
        _record_logout,
        weak=False,
        dispatch_uid="bankingsys_audit_auth_logout",
    )
