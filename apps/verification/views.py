"""
AKHU AFIVS — Verification Views (5-Step Wizard)
"""
import json
import logging
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.conf import settings

from apps.verification.models import (
    VerificationSession, FaceProfile, LivenessChallenge,
    VerificationStatus, VerificationStep
)
from apps.accounts.models import ApplicantProfile, CustomUser, UserRole, PreRegisteredApplicant
from apps.verification.forms import PersonalInfoForm
from apps.liveness.detector import generate_challenge_sequence, get_challenge_instruction
from apps.qr_module.generator import generate_qr_code

logger = logging.getLogger(__name__)


def _get_or_create_session(request) -> VerificationSession:
    """Get active session from request or create a new one."""
    session_id = request.session.get('verification_session_id')
    if session_id:
        try:
            session = VerificationSession.objects.get(id=session_id)
            if session.status == VerificationStatus.IN_PROGRESS:
                return session
        except VerificationSession.DoesNotExist:
            pass

    session = VerificationSession.objects.create(
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        expires_at=timezone.now() + timedelta(hours=2),
    )
    request.session['verification_session_id'] = str(session.id)
    return session


class HomeView(TemplateView):
    """Public landing page."""
    template_name = 'public/home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = _('AKHU Face Identity Verification System')
        return ctx


class StartVerificationView(View):
    """Step 1 redirect — clears old session and starts fresh."""

    def get(self, request):
        # Clear old session
        if 'verification_session_id' in request.session:
            del request.session['verification_session_id']
        session = _get_or_create_session(request)
        return redirect('verification:step1')


class Step1PersonalInfoView(View):
    """Step 1/5 — Personal information form."""
    template_name = 'public/step1_personal_info.html'

    def _get_session(self, request):
        return _get_or_create_session(request)

    def get(self, request):
        session = self._get_session(request)
        if session.user and hasattr(session.user, 'applicant_profile'):
            profile = session.user.applicant_profile
            if profile.is_locked:
                fp = FaceProfile.objects.filter(session__user=session.user, status='verified').first()
                if not fp:
                    fp = FaceProfile.objects.filter(session__user=session.user).first()
                if fp:
                    request.session['verification_session_id'] = str(fp.session.id)
                    return redirect('verification:result')

        initial_data = {}
        if session.user and hasattr(session.user, 'applicant_profile'):
            profile = session.user.applicant_profile
            initial_data = {
                'surname': profile.last_name,
                'given_name': profile.first_name,
                'passport_number': profile.passport_number,
                'selected_region': profile.selected_region,
            }
        form = PersonalInfoForm(initial=initial_data)
        return render(request, self.template_name, {
            'form': form,
            'session': session,
            'step': 1,
            'page_title': _('Personal Information'),
        })

    def post(self, request):
        session = self._get_session(request)
        form = PersonalInfoForm(request.POST)
        if form.is_valid():
            surname = form.cleaned_data['surname'].strip()
            given_name = form.cleaned_data['given_name'].strip()
            passport_no = form.cleaned_data['passport_number'].strip().upper()
            selected_region = form.cleaned_data['selected_region']

            # ── VERIFIED APPLICANT GUARD ──────────────────────────────────────
            # If this passport already belongs to a completed enrollment, redirect
            # them to the result page so they can download their permit.
            existing_profiles = ApplicantProfile.objects.filter(passport_number=passport_no)
            if existing_profiles.filter(is_locked=True).exists():
                locked_profile = existing_profiles.filter(is_locked=True).first()
                
                # Check that entered surname, given name, and region match the locked profile
                if (locked_profile.last_name.strip().lower() != surname.lower() or 
                        locked_profile.first_name.strip().lower() != given_name.lower() or
                        locked_profile.selected_region != selected_region):
                    form.add_error(
                        None,
                        _('The entered Surname, Given Name, or Region does not match our records for this Passport / Card Number.')
                    )
                    return render(request, self.template_name, {
                        'form': form,
                        'session': session,
                        'step': 1,
                        'page_title': _('Personal Information'),
                    })
                
                # Retrieve the verified face profile and set the session id in Django session
                fp = FaceProfile.objects.filter(session__user=locked_profile.user, status='verified').first()
                if not fp:
                    fp = FaceProfile.objects.filter(session__user=locked_profile.user).first()
                
                if fp:
                    request.session['verification_session_id'] = str(fp.session.id)
                    return redirect('verification:result')
                else:
                    form.add_error(
                        None,
                        _('Your biometric enrollment is already complete, but no verified biometric profile was found. Please contact administrator.')
                    )
                    return render(request, self.template_name, {
                        'form': form,
                        'session': session,
                        'step': 1,
                        'page_title': _('Personal Information'),
                    })

            # Lookup pre-registered applicant
            try:
                allowed_candidate = PreRegisteredApplicant.objects.get(passport_number=passport_no)
            except PreRegisteredApplicant.DoesNotExist:
                form.add_error('passport_number', _('Passport / Card Number not found in the allowed applicant list. Please contact administrator.'))
                return render(request, self.template_name, {
                    'form': form,
                    'session': session,
                    'step': 1,
                    'page_title': _('Personal Information'),
                })

            # Case-insensitive name match validation
            if allowed_candidate.surname.strip().lower() != surname.lower() or allowed_candidate.given_name.strip().lower() != given_name.lower():
                form.add_error(None, _('The entered Surname or Given Name does not match our pre-registered records for this Passport / Card Number.'))
                return render(request, self.template_name, {
                    'form': form,
                    'session': session,
                    'step': 1,
                    'page_title': _('Personal Information'),
                })



            # Clean up any partial old records to prevent duplicate key or username conflicts.
            # First, remove temporary biometric data from any previous incomplete enrollment —
            # CASCADE will delete DB rows but media files on disk must be deleted explicitly.
            temp_username = f'applicant_{passport_no}'
            from django.contrib.auth import get_user_model
            _OldUser = get_user_model()
            try:
                _old_user = _OldUser.objects.get(username=temp_username)
                from apps.verification.cleanup import cleanup_all_incomplete_for_user
                cleanup_all_incomplete_for_user(
                    _old_user,
                    reason='new_enrollment',
                    performed_by='system',
                )
            except _OldUser.DoesNotExist:
                pass
            except Exception as _ce:
                import logging as _lg
                _lg.getLogger(__name__).warning("Biometric cleanup on new enrollment failed: %s", _ce)
            CustomUser.objects.filter(username=temp_username).delete()
            ApplicantProfile.objects.filter(passport_number=passport_no).delete()

            # Create User
            user = CustomUser.objects.create_user(
                username=temp_username,
                role=UserRole.APPLICANT,
            )
            session.user = user
            session.current_step = VerificationStep.DOCUMENT_UPLOAD
            session.step_personal_info_done = True
            session.step_document_done = False
            session.save()

            # Create ApplicantProfile using details from PreRegisteredApplicant and selected region
            ApplicantProfile.objects.create(
                user=user,
                first_name=allowed_candidate.given_name,
                last_name=allowed_candidate.surname,
                middle_name=allowed_candidate.middle_name,
                passport_number=passport_no,
                admission_id=f'TEMP-{passport_no}',
                applicant_id=allowed_candidate.applicant_id,
                program=allowed_candidate.program,
                selected_region=selected_region or allowed_candidate.region,
            )

            FaceProfile.objects.create(
                session=session,
            )

            return redirect('verification:step2')

        return render(request, self.template_name, {
            'form': form,
            'session': session,
            'step': 1,
            'page_title': _('Personal Information'),
        })


class Step2DocumentUploadView(View):
    """Step 2/5 — Passport/ID upload."""
    template_name = 'public/step2_document_upload.html'

    def get(self, request):
        session = _get_or_create_session(request)
        if not session.step_personal_info_done:
            return redirect('verification:step1')
        return render(request, self.template_name, {
            'session': session,
            'step': 2,
            'page_title': _('Upload Identity Document'),
        })

    def post(self, request):
        session = _get_or_create_session(request)
        if not session.step_personal_info_done:
            return redirect('verification:step1')

        document_file = request.FILES.get('document')
        if not document_file:
            messages.error(request, _('Please select a document file to upload.'))
            return render(request, self.template_name, {
                'session': session,
                'step': 2,
                'page_title': _('Upload Identity Document'),
            })

        # Save document file to the ApplicantProfile
        if session.user and hasattr(session.user, 'applicant_profile'):
            profile = session.user.applicant_profile
            profile.passport_image = document_file
            profile.save(update_fields=['passport_image'])

        session.current_step = VerificationStep.FACE_CAPTURE
        session.step_document_done = True
        session.save()

        return redirect('verification:step3')


class Step3FaceCaptureView(TemplateView):
    """Step 3/5 — Live selfie capture via webcam."""
    template_name = 'public/step3_face_capture.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = _get_or_create_session(self.request)
        ctx.update({'session': session, 'step': 3, 'page_title': _('Face Capture')})
        return ctx

    def get(self, request, *args, **kwargs):
        session = _get_or_create_session(request)
        if not session.step_document_done:
            return redirect('verification:step2')
        return super().get(request, *args, **kwargs)


class Step4LivenessView(TemplateView):
    """Step 4/5 — Liveness detection challenges."""
    template_name = 'public/step4_liveness.html'

    def get(self, request, *args, **kwargs):
        session = _get_or_create_session(request)
        if not session.step_face_capture_done:
            return redirect('verification:step3')

        # Generate challenges for this session
        challenges = generate_challenge_sequence()
        lang = request.LANGUAGE_CODE or 'en'
        challenge_data = [
            {
                'type': c,
                'instruction': get_challenge_instruction(c, lang),
                'order': i,
            }
            for i, c in enumerate(challenges)
        ]
        # Store in session
        request.session['liveness_challenges'] = challenges

        return render(request, self.template_name, {
            'session': session,
            'step': 4,
            'challenges': challenge_data,
            'challenges_json': json.dumps(challenge_data),
            'page_title': _('Multi-Angle Face Capture'),
        })


class Step5ResultView(TemplateView):
    """Step 5/5 — Display verification result."""
    template_name = 'public/step5_result.html'

    def get(self, request, *args, **kwargs):
        session_id = request.session.get('verification_session_id')
        if not session_id:
            return redirect('verification:home')

        try:
            session = VerificationSession.objects.get(id=session_id)
        except VerificationSession.DoesNotExist:
            return redirect('verification:home')

        face_profile = getattr(session, 'face_profile', None)
        if not face_profile and session.user:
            from apps.verification.models import FaceProfile
            face_profile = FaceProfile.objects.filter(
                session__user=session.user,
                status='verified'
            ).first()

        context = {
            'session': session,
            'face_profile': face_profile,
            'step': 5,
            'page_title': _('Verification Result'),
        }

        if face_profile:
            context['status'] = face_profile.status
            context['match_percentage'] = face_profile.match_percentage
            context['qr_code'] = None

            # Dynamic check for permit readiness based only on permits_released setting
            from apps.accounts.models import check_permit_ready, SystemSetting
            permit_ready = check_permit_ready()
            
            setting = SystemSetting.objects.first()
            release_date_str = ""
            if setting and setting.permit_release_date:
                release_date_str = setting.permit_release_date.strftime('%d.%m.%Y')

            context.update({
                'permit_ready': permit_ready,
                'release_date_str': release_date_str,
            })

            if face_profile.status == 'verified' and permit_ready:
                # Read ONLY existing QR code from database. Never create one.
                profile = session.user.applicant_profile if hasattr(session.user, 'applicant_profile') else None
                if profile:
                    from apps.qr_module.models import QRCode
                    try:
                        context['qr_code'] = profile.qr_code
                    except QRCode.DoesNotExist:
                        context['qr_code'] = None

        return render(request, self.template_name, context)


class DownloadConfirmationView(View):
    """Download PDF confirmation of verification."""

    def get(self, request, session_id):
        session = get_object_or_404(VerificationSession, id=session_id)
        face_profile = getattr(session, 'face_profile', None)
        if not face_profile and session.user:
            from apps.verification.models import FaceProfile
            face_profile = FaceProfile.objects.filter(
                session__user=session.user,
                status='verified'
            ).first()

        if not face_profile or face_profile.status not in ('verified', 'review_required'):
            messages.error(request, _('Verification not complete'))
            return redirect('verification:home')

        # Permit release check for normal applicants
        from apps.admin_panel.views import ADMIN_SESSION_KEY
        is_admin = request.session.get(ADMIN_SESSION_KEY) or (request.user.is_authenticated and getattr(request.user, 'is_staff', False))
        
        if not is_admin:
            from apps.accounts.models import check_permit_ready
            if not check_permit_ready():
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(_('Admission permits are not yet released.'))

        from apps.reports.views import generate_confirmation_pdf
        return generate_confirmation_pdf(session)


def custom_handler404(request, exception=None):
    return render(request, '404.html', status=404)


def custom_handler500(request):
    return render(request, '500.html', status=500)
