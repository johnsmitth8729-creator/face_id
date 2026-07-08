"""AKHU AFIVS — Supervisor API URLs"""
from django.urls import path
from apps.supervisor import api

urlpatterns = [
    path('exam-verify/', api.SupervisorExamVerifyAPI.as_view(), name='exam-verify'),
    path('exam-identify/', api.SupervisorExamIdentifyAPI.as_view(), name='exam-identify'),
    path('qr-scan/', api.SupervisorQRScanAPI.as_view(), name='qr-scan'),
    path('confirm-attendance/', api.ConfirmAttendanceAPI.as_view(), name='confirm-attendance'),
]
