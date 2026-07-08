"""AKHU AFIVS — QR Module Views"""
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.utils.translation import gettext_lazy as _

from apps.qr_module.generator import scan_qr_token


class QRVerifyView(View):
    """Public QR verification page — shows applicant status."""
    template_name = 'public/qr_verify.html'

    def get(self, request, token):
        result = scan_qr_token(token)

        if result.get('valid'):
            public_title = _('QR Code Confirmed')
            public_message = _('This QR code has been verified by the university platform.')
        elif result.get('error') == 'QR code not found':
            public_title = _('QR Code Not Found')
            public_message = _('This QR code was not found in the platform database.')
        else:
            public_title = _('QR Code Not Valid')
            public_message = _('This QR code is not valid or is no longer active.')

        return render(request, self.template_name, {
            'result': result,
            'token': token,
            'public_title': public_title,
            'public_message': public_message,
            'page_title': _('QR Verification'),
        })


class QRScanAPIView(View):
    """API endpoint for QR token lookup."""
    def post(self, request):
        try:
            data = json.loads(request.body)
            token = data.get('token', '').strip()
            result = scan_qr_token(token)
            return JsonResponse(result)
        except Exception as e:
            return JsonResponse({'valid': False, 'error': str(e)}, status=500)
