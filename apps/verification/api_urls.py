"""AKHU AFIVS — Verification API URL configuration"""
from django.urls import path
from apps.verification import api

urlpatterns = [
    path('save-selfie/', api.SaveSelfieAPI.as_view(), name='save-selfie'),
    path('liveness/verify/', api.LivenessChallengeAPI.as_view(), name='liveness-verify'),
    path('liveness/complete/', api.CompleteLivenessAPI.as_view(), name='liveness-complete'),
    path('match/', api.FaceMatchAPI.as_view(), name='face-match'),
    path('detect-face/', api.DetectFaceInFrameAPI.as_view(), name='detect-face'),
    path('status/<uuid:session_id>/', api.VerificationStatusAPI.as_view(), name='status'),
]
