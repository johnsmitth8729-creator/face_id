"""
AKHU AFIVS — Audit Middleware
Automatically logs all significant HTTP requests to AuditLog.
"""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

# Paths to skip logging (static/media/health)
SKIP_PATHS = [
    '/static/', '/media/', '/favicon.ico', '/__debug__/',
    '/django-admin/jsi18n/', '/health/',
]

# Actions to always log regardless of method
ALWAYS_LOG_PATHS = [
    '/supervisor/', '/admin-panel/', '/api/',
]


class AuditLogMiddleware:
    """
    Middleware that logs user actions to AuditLog.
    Logs: logins, logouts, verifications, admin actions, supervisor actions.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Skip irrelevant paths
        path = request.path
        if any(path.startswith(skip) for skip in SKIP_PATHS):
            return response

        # Only log POST/PUT/DELETE or always-log paths
        should_log = (
            request.method in ('POST', 'PUT', 'DELETE', 'PATCH') or
            any(path.startswith(p) for p in ALWAYS_LOG_PATHS)
        )

        if should_log:
            self._log_request(request, response)

        return response

    def _log_request(self, request, response):
        try:
            from apps.audit.models import AuditLog

            user = request.user if request.user.is_authenticated else None
            username = user.username if user else 'anonymous'
            role = user.role if user else ''

            path = request.path
            category = self._get_category(path)
            action = f'{request.method} {path}'
            success = response.status_code < 400

            AuditLog.objects.create(
                user=user,
                username_snapshot=username,
                user_role_snapshot=role,
                category=category,
                action=action,
                ip_address=self._get_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                method=request.method,
                path=path,
                success=success,
                error_message='' if success else f'HTTP {response.status_code}',
            )
        except Exception as e:
            logger.error(f'AuditLog middleware error: {e}')

    def _get_category(self, path: str) -> str:
        if '/supervisor/' in path:
            return 'supervisor'
        if '/admin-panel/' in path or '/admin/' in path:
            return 'admin'
        if '/api/verification/' in path or '/verification/' in path:
            return 'verification'
        if '/login' in path or '/logout' in path:
            return 'auth'
        if '/reports/' in path:
            return 'report'
        return 'system'

    def _get_ip(self, request) -> str:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')
