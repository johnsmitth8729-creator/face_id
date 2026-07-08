"""AKHU AFIVS — Reports URL patterns"""
from django.urls import path
from apps.reports import views

app_name = 'reports'

urlpatterns = [
    path('export/<str:report_type>/<str:fmt>/', views.ExportReportView.as_view(), name='export'),
]
