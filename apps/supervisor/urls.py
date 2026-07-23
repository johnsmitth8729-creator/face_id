"""AKHU AFIVS — Supervisor URL patterns"""
from django.urls import path
from apps.supervisor import views
from apps.supervisor import api

app_name = 'supervisor'

urlpatterns = [
    path('', views.SupervisorDashboardView.as_view(), name='dashboard'),
    path('login/', views.SupervisorLoginView.as_view(), name='login'),
    path('logout/', views.SupervisorLogoutView.as_view(), name='logout'),
    path('verify/', views.ExamVerifyView.as_view(), name='exam-verify-auto'),
    path('verify/<uuid:profile_id>/', views.ExamVerifyView.as_view(), name='exam-verify'),
    path('permits/', views.SupervisorPermitsView.as_view(), name='permits'),
    path('permits/download/<uuid:profile_id>/', views.SupervisorPermitDownloadView.as_view(), name='permit-download'),
    path('history/<uuid:profile_id>/', views.ApplicantHistoryView.as_view(), name='history'),
    # API endpoints (also accessible here for cleaner routing)
    path('api/qr-lookup/', api.SupervisorQRLookupAPI.as_view(), name='api-qr-lookup'),
    path('api/exam-verify/', api.SupervisorExamVerifyAPI.as_view(), name='api-exam-verify'),
    path('api/confirm-attendance/', api.ConfirmAttendanceAPI.as_view(), name='api-confirm-attendance'),
]

