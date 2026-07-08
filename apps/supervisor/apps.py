"""AKHU AFIVS — Supervisor App Config"""
from django.apps import AppConfig


class SupervisorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.supervisor'
    verbose_name = 'Supervisor Portal'
