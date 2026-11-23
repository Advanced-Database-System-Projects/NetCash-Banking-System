
from django.db import migrations


SYSTEM_ROLES = (
    "Admin",
    "Staff",
    "Loan Officer",
    "Borrower",
)


def create_system_roles(apps, schema_editor):
    Roles = apps.get_model("SysDataBase", "Roles")
    db_alias = schema_editor.connection.alias

    for role_name in SYSTEM_ROLES:
        Roles.objects.using(db_alias).get_or_create(
            roles_name=role_name
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "SysDataBase",
            "0008_alter_notifications_channel",
        ),
    ]

    operations = [
        migrations.RunPython(
            create_system_roles,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
