"""AKHU AFIVS — QR Module URL patterns"""
from django.urls import path
from apps.qr_module import views

app_name = 'qr_module'

urlpatterns = [
    path('qr/<str:token>/', views.QRVerifyView.as_view(), name='qr-verify'),
]
