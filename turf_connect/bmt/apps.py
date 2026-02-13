from django.apps import AppConfig


class BmtConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bmt'

    def ready(self):
        import bmt.signals
