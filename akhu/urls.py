"""AKHU AFIVS — Root URL Configuration"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.urls import path, include
from django.views.generic import RedirectView

from apps.verification.views import custom_handler404, custom_handler500

# Non-i18n patterns (API endpoints, admin, etc.)
urlpatterns = [
    # Redirect standard /admin to custom /admin-panel/
    path('admin/', RedirectView.as_view(url='/admin-panel/', permanent=False)),

    # Django built-in admin (hidden, for internal use only)
    path('django-admin/', admin.site.urls),

    # Language switching
    path('i18n/', include('django.conf.urls.i18n')),

    # Custom error preview routes (accessible in development)
    path('404/', custom_handler404, {'exception': Exception("Page not found preview")}),
    path('500/', custom_handler500),

    # API endpoints (no i18n prefix needed)
    path('api/verification/', include('apps.verification.api_urls')),
    path('api/liveness/', include('apps.liveness.api_urls')),
    path('api/qr/', include('apps.qr_module.api_urls')),
    path('api/supervisor/', include('apps.supervisor.api_urls')),
    path('api/admin/', include('apps.admin_panel.api_urls')),
]

# Set custom error handlers
handler404 = 'apps.verification.views.custom_handler404'
handler500 = 'apps.verification.views.custom_handler500'

# i18n-prefixed patterns (user-facing pages)
urlpatterns += i18n_patterns(
    # Public user-facing pages
    path('', include('apps.verification.urls')),

    # Supervisor portal (hidden, accessed via direct URL)
    path('supervisor/', include('apps.supervisor.urls')),

    # Admin panel (hidden, accessed via direct URL)
    path('admin-panel/', include('apps.admin_panel.urls')),

    # QR verification
    path('verify/', include('apps.qr_module.urls')),

    # Reports
    path('reports/', include('apps.reports.urls')),

    prefix_default_language=False,
)

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Debug toolbar
    if 'debug_toolbar' in getattr(settings, 'INSTALLED_APPS', []):
        try:
            import debug_toolbar
            urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
        except ImportError:
            pass
