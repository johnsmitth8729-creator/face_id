"""AKHU AFIVS — QR Module API URLs"""
from django.urls import path
from apps.qr_module import views

urlpatterns = [
    path('scan/', views.QRScanAPIView.as_view(), name='qr-scan-api'),
]
