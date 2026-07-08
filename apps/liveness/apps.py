"""AKHU AFIVS — Liveness App Config"""
from django.apps import AppConfig


class LivenessConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.liveness'
    verbose_name = 'Liveness Detection'
