"""AKHU AFIVS — Admin Panel URL patterns"""
from django.urls import path
from apps.admin_panel import views

app_name = 'admin_panel'

urlpatterns = [
    path('', views.AdminDashboardView.as_view(), name='dashboard'),
    path('login/', views.AdminLoginView.as_view(), name='login'),
    path('logout/', views.AdminLogoutView.as_view(), name='logout'),
    path('applicants/', views.ApplicantListView.as_view(), name='applicants'),
    path('permits/', views.PermitsManagementView.as_view(), name='permits'),
    path('permits/download-zip/', views.DownloadAllPermitsZipView.as_view(), name='permits-download-zip'),
    path('liveness/', views.LivenessBiometricsView.as_view(), name='liveness-biometrics'),
    path('liveness/download-zip/', views.DownloadAllLivenessZipView.as_view(), name='liveness-download-all-zip'),
    path('liveness/<uuid:profile_id>/download-zip/', views.DownloadLivenessZipView.as_view(), name='liveness-download-zip'),
    path('attendance/', views.AttendanceManagementView.as_view(), name='attendance'),
    path('attendance/export-excel/', views.AttendanceExportExcelView.as_view(), name='attendance-export-excel'),
    path('supervisors/', views.SupervisorManagementView.as_view(), name='supervisors'),
    path('qr/', views.QRManagementView.as_view(), name='qr-management'),
    path('audit/', views.AuditLogView.as_view(), name='audit-logs'),
    path('ai-config/', views.AIConfigView.as_view(), name='ai-config'),
    path('settings/', views.SystemSettingsView.as_view(), name='settings'),
    path('reports/', views.ReportsView.as_view(), name='reports'),
]
