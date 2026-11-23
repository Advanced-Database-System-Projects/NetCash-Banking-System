"""Associate database changes with the signed-in user per request.

Also record HTTP mutation attempts, including denied attempts, without storing
request bodies or credentials. A REQUEST entry does not mean a change succeeded.
"""
import logging

from django.db import DatabaseError

from .audit_signals import start_actor, stop_actor, write_audit

logger = logging.getLogger(__name__)


class AuditActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        actor_id = user.pk if user is not None and user.is_authenticated else None
        token = start_actor(actor_id)
        try:
            response = self.get_response(request)
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                # Describes the HTTP request and status only; POST 302 may also
                # be a rejected form, so this is NOT an approval/success log.
                resolved = getattr(request, "resolver_match", None)
                route = (resolved.url_name if resolved else None) or "UnknownRoute"
                ids = (resolved.kwargs if resolved else {}) or {}
                target_id = next(
                    (str(value) for name, value in ids.items() if name.endswith("_id")),
                    "",
                )
                try:
                    user = getattr(request, "user", None)
                    post_actor = user.pk if user is not None and user.is_authenticated else None
                    write_audit(
                        f"REQUEST_{request.method}_{response.status_code}",
                        route,
                        target_id,
                        user_id=post_actor,
                    )
                except DatabaseError:
                    # Audit failure must not turn an already-committed banking
                    # transaction into a misleading HTTP 500 response.
                    logger.exception("Could not record BankingSys HTTP audit event")
            return response
        finally:
            stop_actor(token)
