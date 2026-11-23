"""Focused tests for the audit trail. Run: python manage.py test SysDataBase.test_audit_trail"""
from django.test import TestCase
from django.urls import reverse

from .models import Audit_logs, Roles, User


class AuditTrailTests(TestCase):
    def setUp(self):
        role, _ = Roles.objects.get_or_create(roles_name="Admin")
        self.admin = User.objects.create_user(
            username="auditadmin", email="auditadmin@example.com",
            password="TestPass2026!", roles=role, is_staff=True,
        )
        self.borrower = User.objects.create_user(
            username="auditborrower", email="auditborrower@example.com",
            password="TestPass2026!",
        )

    def test_creates_and_updates_are_logged(self):
        self.assertTrue(Audit_logs.objects.filter(
            action="CREATE", entity_name="User", entity_id=str(self.borrower.pk)
        ).exists())
        self.borrower.first_name = "Sample"
        self.borrower.save(update_fields=["first_name"])
        self.assertTrue(Audit_logs.objects.filter(
            action="UPDATE", entity_name="User", entity_id=str(self.borrower.pk)
        ).exists())

    def test_only_admin_can_view_and_export(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get(reverse("audit_log_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("audit_log_export")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("audit_log_list")).status_code, 200)
        response = self.client.get(reverse("audit_log_export"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn(b"Timestamp,Username,Action", response.content)
