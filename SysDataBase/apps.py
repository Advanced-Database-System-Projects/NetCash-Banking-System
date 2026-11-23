from django.apps import AppConfig


class SysdatabaseConfig(AppConfig):
    name = 'SysDataBase'

    def ready(self):
        from . import notification_signals  # noqa: F401

