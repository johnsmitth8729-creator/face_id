"""
AKHU AFIVS — Context Processors
"""
from django.conf import settings


def site_settings(request):
    """Inject global site settings into all templates."""
    return {
        'SITE_NAME': getattr(settings, 'SITE_NAME', 'AKHU Face Verification System'),
        'SITE_URL': getattr(settings, 'SITE_URL', 'https://faceid.akhu.uz'),
        'INSTITUTION_NAME': getattr(settings, 'INSTITUTION_NAME', 'Andijan Khusan University'),
        'CURRENT_YEAR': __import__('datetime').datetime.now().year,
    }
