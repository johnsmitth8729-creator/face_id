"""AKHU AFIVS — Verification URL configuration"""
from django.urls import path
from apps.verification import views

app_name = 'verification'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('start/', views.StartVerificationView.as_view(), name='start'),
    path('step/1/', views.Step1PersonalInfoView.as_view(), name='step1'),
    path('step/consent/', views.StepConsentView.as_view(), name='consent'),
    path('step/2/', views.Step3FaceCaptureView.as_view(), name='step2'),
    path('step/3/', views.Step4LivenessView.as_view(), name='step3'),
    path('result/', views.Step5ResultView.as_view(), name='result'),
    path('download/<uuid:session_id>/', views.DownloadConfirmationView.as_view(), name='download'),
]
