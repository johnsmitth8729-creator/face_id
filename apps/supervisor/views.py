"""
AKHU AFIVS — Supervisor Portal Views
Login, Dashboard, Exam-Day Verification, History
"""
import logging
from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import authenticate
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.models import CustomUser, ApplicantProfile, UserRole
from apps.verification.models import VerificationLog, FaceProfile
from apps.face_engine.engine import get_face_engine, determine_verification_status

logger = logging.getLogger(__name__)

SUPERVISOR_SESSION_KEY = 'supervisor_authenticated'


def supervisor_required(view_func):
    """Decorator: require supervisor session."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get(SUPERVISOR_SESSION_KEY):
            return redirect(settings.SUPERVISOR_LOGIN_URL)
        return view_func(request, *args, **kwargs)
    return wrapper


def supervisor_required_class(cls):
    """Class-based view decorator for supervisor auth."""
    original_dispatch = cls.dispatch

    def new_dispatch(self, request, *args, **kwargs):
        if not request.session.get(SUPERVISOR_SESSION_KEY):
            return redirect(settings.SUPERVISOR_LOGIN_URL)
        return original_dispatch(self, request, *args, **kwargs)

    cls.dispatch = new_dispatch
    return cls


class SupervisorLoginView(View):
    """Supervisor login page."""
    template_name = 'supervisor/login.html'

    def get(self, request):
        if request.session.get(SUPERVISOR_SESSION_KEY):
            return redirect('supervisor:dashboard')
        return render(request, self.template_name, {
            'page_title': _('Supervisor Login'),
        })

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        if not username or not password:
            messages.error(request, _('Please enter username and password'))
            return render(request, self.template_name, {'page_title': _('Supervisor Login')})

        user = authenticate(request, username=username, password=password)
        if user and user.role == UserRole.SUPERVISOR and user.is_active:
            # Update supervisor last activity
            if hasattr(user, 'supervisor_account'):
                user.supervisor_account.last_activity = timezone.now()
                user.supervisor_account.save()

            request.session[SUPERVISOR_SESSION_KEY] = True
            request.session['supervisor_user_id'] = str(user.id)
            request.session['supervisor_username'] = user.username
            user.last_login_ip = request.META.get('REMOTE_ADDR')
            user.save()

            logger.info(f'Supervisor login: {username}')
            return redirect('supervisor:dashboard')

        messages.error(request, _('Invalid credentials or insufficient permissions'))
        return render(request, self.template_name, {'page_title': _('Supervisor Login')})


class SupervisorLogoutView(View):
    def get(self, request):
        request.session.pop(SUPERVISOR_SESSION_KEY, None)
        request.session.pop('supervisor_user_id', None)
        request.session.pop('supervisor_username', None)
        return redirect('supervisor:login')


@supervisor_required_class
class SupervisorDashboardView(TemplateView):
    """Supervisor main dashboard — search applicants."""
    template_name = 'supervisor/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        query = self.request.GET.get('q', '').strip()
        results = []

        if query:
            results = ApplicantProfile.objects.filter(
                Q(admission_id__icontains=query) |
                Q(passport_number__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            ).select_related('user', 'qr_code').order_by('-created_at')[:50]

        # Today's stats
        today = timezone.now().date()
        today_verifications = VerificationLog.objects.filter(
            verification_type='exam_day',
            verified_at__date=today,
        )

        ctx.update({
            'page_title': _('Supervisor Dashboard'),
            'query': query,
            'results': results,
            'today_total': today_verifications.count(),
            'today_verified': today_verifications.filter(result='verified').count(),
            'today_failed': today_verifications.filter(result='rejected').count(),
            'today_review': today_verifications.filter(result='review_required').count(),
        })
        return ctx


@supervisor_required_class
class ExamVerifyView(View):
    """Exam-day live camera verification page."""
    template_name = 'supervisor/exam_verify.html'

    def get(self, request, profile_id=None):
        applicant = None
        selfie_url = ""
        if profile_id:
            applicant = get_object_or_404(ApplicantProfile, id=profile_id)
            from apps.verification.models import FaceProfile
            face_prof = FaceProfile.objects.filter(session__user=applicant.user, status='verified').first()
            if not face_prof:
                face_prof = FaceProfile.objects.filter(session__user=applicant.user).first()
            if face_prof and face_prof.selfie_image:
                selfie_url = face_prof.selfie_image.url

        return render(request, self.template_name, {
            'page_title': _('Exam Day Verification'),
            'applicant': applicant,
            'selfie_url': selfie_url,
        })


@supervisor_required_class
class ApplicantHistoryView(View):
    """Verification history for a specific applicant."""
    template_name = 'supervisor/history.html'

    def get(self, request, profile_id):
        profile = get_object_or_404(ApplicantProfile, id=profile_id)
        logs = VerificationLog.objects.filter(
            applicant_profile=profile
        ).order_by('-verified_at')

        paginator = Paginator(logs, 20)
        page = paginator.get_page(request.GET.get('page'))

        face_profiles = FaceProfile.objects.filter(
            session__user=profile.user
        ).order_by('-created_at')

        return render(request, self.template_name, {
            'page_title': _('Verification History'),
            'profile': profile,
            'logs': page,
            'face_profiles': face_profiles,
        })


@supervisor_required_class
class SupervisorPermitsView(View):
    """Supervisor Permits page — search verified candidates and download their permit PDFs."""
    template_name = 'supervisor/permits.html'

    def get(self, request):
        query = request.GET.get('q', '').strip()

        applicants = ApplicantProfile.objects.filter(
            Q(is_locked=True) | Q(user__verification_sessions__face_profile__status='verified')
        ).select_related('user').prefetch_related(
            'user__verification_sessions__face_profile', 'qr_code'
        ).distinct().order_by('-created_at')

        if query:
            import re
            words = query.split()
            clean_alnum = re.sub(r'[^A-Za-z0-9]', '', query)
            clean_digits = re.sub(r'\D', '', query)

            q_objects = Q()

            # 1. Direct field match for raw query
            raw_q = (
                Q(admission_id__icontains=query) |
                Q(applicant_id__icontains=query) |
                Q(passport_number__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(middle_name__icontains=query) |
                Q(program__icontains=query) |
                Q(selected_region__icontains=query) |
                Q(exam_venue__icontains=query)
            )
            q_objects |= raw_q

            # 2. Passport clean string match (e.g., "AA 1234567" or "aa1234567")
            if clean_alnum and len(clean_alnum) >= 3:
                q_objects |= Q(passport_number__icontains=clean_alnum)
                q_objects |= Q(admission_id__icontains=clean_alnum)

            # 3. Numeric ID matching (e.g. "0001" or "12")
            if clean_digits:
                q_objects |= Q(admission_id__icontains=clean_digits)
                q_objects |= Q(applicant_id__icontains=clean_digits)

            # 4. Multi-word search (e.g. "John Doe" or "Toshkent Aliyev")
            if len(words) > 1:
                word_q = Q()
                for w in words:
                    sub_q = (
                        Q(first_name__icontains=w) |
                        Q(last_name__icontains=w) |
                        Q(middle_name__icontains=w) |
                        Q(passport_number__icontains=w) |
                        Q(admission_id__icontains=w) |
                        Q(selected_region__icontains=w) |
                        Q(program__icontains=w)
                    )
                    if not word_q:
                        word_q = sub_q
                    else:
                        word_q &= sub_q
                q_objects |= word_q

            applicants = applicants.filter(q_objects)

        paginator = Paginator(applicants, 20)
        page = paginator.get_page(request.GET.get('page'))

        return render(request, self.template_name, {
            'page_title': _('Candidate Permits'),
            'applicants': page,
            'query': query,
            'active': 'permits',
        })


@supervisor_required_class
class SupervisorPermitDownloadView(View):
    """Download single candidate admission permit PDF."""
    def get(self, request, profile_id):
        profile = get_object_or_404(ApplicantProfile.objects.select_related('user'), id=profile_id)

        # Ensure candidate has QR generated
        try:
            from apps.qr_module.services import generate_applicant_qr
            generate_applicant_qr(profile)
            profile.refresh_from_db()
        except Exception as e:
            logger.warning(f"Supervisor permit QR generation check: {e}")

        session = profile.user.verification_sessions.filter(
            face_profile__status='verified'
        ).first()

        if not session:
            session = profile.user.verification_sessions.order_by('-started_at').first()

        if not session:
            messages.error(request, _('No verification session found for this candidate.'))
            return redirect('supervisor:permits')

        from apps.reports.views import generate_confirmation_pdf
        return generate_confirmation_pdf(session)
