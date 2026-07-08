import logging
from django.conf import settings
from django.http import Http404
from django.shortcuts import render

logger = logging.getLogger(__name__)

class CustomDebugErrorMiddleware:
    """
    Middleware to force rendering of custom 404 and 500 error pages
    even when settings.DEBUG is True, providing a consistent user experience
    during testing and development.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Intercept 404 status code in DEBUG mode for HTML page requests
        if response.status_code == 404 and settings.DEBUG:
            # Avoid intercepting API, static, or media paths
            if not any(request.path.startswith(prefix) for prefix in ['/api/', '/static/', '/media/', '/__debug__/']):
                from apps.verification.views import custom_handler404
                try:
                    return custom_handler404(request)
                except Exception as e:
                    logger.error(f"Error rendering custom 404 in debug mode: {e}")
        
        return response

    def process_exception(self, request, exception):
        # Catch Http404 exceptions directly
        if isinstance(exception, Http404) and settings.DEBUG:
            if not any(request.path.startswith(prefix) for prefix in ['/api/', '/static/', '/media/', '/__debug__/']):
                from apps.verification.views import custom_handler404
                try:
                    return custom_handler404(request, exception)
                except Exception as e:
                    logger.error(f"Error rendering custom 404 from exception: {e}")
        
        # If there's a 500 error in DEBUG mode, we normally want the yellow debug traceback screen,
        # but if we want to preview the 500 error page we let the developer visit '/500/'.
        # We return None so Django's default exception handling (traceback) proceeds for other exceptions.
        return None
