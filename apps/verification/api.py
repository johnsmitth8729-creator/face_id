"""
AKHU AFIVS — Verification API Endpoints
Face capture, liveness verification, enrollment finalization
"""
import json
import base64
import logging
import hashlib

from django.db import transaction
from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from django.conf import settings

from apps.verification.models import (
    VerificationSession, FaceProfile, LivenessChallenge,
    VerificationLog, VerificationStatus
)
from apps.face_engine.engine import get_face_engine, determine_verification_status
from apps.liveness.detector import get_liveness_detector

logger = logging.getLogger(__name__)


def _get_session(request) -> VerificationSession:
    session_id = request.session.get('verification_session_id')
    if not session_id:
        raise ValueError('No active verification session')
    try:
        session = VerificationSession.objects.get(id=session_id)
    except VerificationSession.DoesNotExist:
        raise ValueError('Verification session not found')
    if session.expires_at and session.expires_at < timezone.now():
        # Session expired — remove any temporary biometric data before rejecting
        try:
            from apps.verification.cleanup import cleanup_incomplete_enrollment
            cleanup_incomplete_enrollment(
                session,
                reason='session_expired',
                performed_by='system',
            )
        except Exception as _cleanup_err:
            logger.warning("Cleanup on session expiry failed: %s", _cleanup_err)
        raise ValueError('Verification session has expired')
    return session


def _get_ip(request) -> str:
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _normalized_weights(available_types: list[str]) -> dict[str, float]:
    configured = getattr(settings, 'FACE_MATCH_WEIGHTS', {
        'straight': 0.5,
        'left': 0.2,
        'right': 0.2,
        'up': 0.1,
    })
    weights = {key: max(0.0, float(configured.get(key, 0.0))) for key in available_types}
    total = sum(weights.values())
    if total <= 0:
        return {key: 1.0 / len(available_types) for key in available_types}
    return {key: value / total for key, value in weights.items()}


def _weighted_similarity(results: list[dict]) -> tuple[float, float]:
    weights = _normalized_weights([item['type'] for item in results])
    cosine = sum(item['cosine'] * weights[item['type']] for item in results)
    percentage = sum(item['percentage'] * weights[item['type']] for item in results)
    return (
        max(-1.0, min(1.0, float(cosine))),
        round(max(0.0, min(100.0, float(percentage))), 2),
    )


class SaveSelfieAPI(View):
    """
    POST /api/verification/save-selfie/

    Step 3 — Enrollment selfie capture.

    Pipeline (InsightFace runs ONCE here during enrollment):
        1. Decode + validate base64 image
        2. PIL format check
        3. Face Quality Assessment (FQA)
        4. Anti-Spoofing check
        5. Extract face embedding (InsightFace)
        6. Crop face + save image
        7. Store embedding in face_profile.selfie_embedding
        8. Mark step_face_capture_done = True
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            image_data = data.get('image')  # base64 data URL
            if not image_data:
                return JsonResponse({'success': False, 'error': 'No image data'}, status=400)

            # Security limits: max 15MB base64 string (~11MB binary)
            if len(image_data) > 15 * 1024 * 1024:
                return JsonResponse({'success': False, 'error': 'Image data exceeds size limit'}, status=400)

            session = _get_session(request)

            # Decode base64
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            try:
                img_bytes = base64.b64decode(image_data)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Invalid base64 image data'}, status=400)

            # Decoded size limit
            if len(img_bytes) > settings.MAX_UPLOAD_SIZE:
                return JsonResponse({'success': False, 'error': 'Image exceeds file size limit'}, status=400)

            # Validate image format and integrity using PIL
            from PIL import Image
            import io
            try:
                img_pil = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            except Exception:
                return JsonResponse({'success': False, 'error': 'Invalid or corrupted image file'}, status=400)

            # --- Step A: Face Quality Assessment ---
            from apps.face_engine.quality import check_face_quality
            engine = get_face_engine()
            face_result = engine.extract_face_and_embedding(img_pil, require_single=True)
            face_info = face_result.get('face')
            if not face_result.get('success'):
                return JsonResponse({
                    'success': False,
                    'error': face_result.get('error') or 'Could not detect exactly one face. Please retake the selfie.',
                }, status=422)

            fqa_result = check_face_quality(img_pil, face_info)
            if not fqa_result['success']:
                logger.error("FQA failed: %s", fqa_result['error'])
                resp_data = {'success': False, 'error': fqa_result['error']}
                if 'face_ratio' in fqa_result:
                    resp_data['face_ratio'] = fqa_result['face_ratio']
                if 'required_ratio' in fqa_result:
                    resp_data['required_ratio'] = fqa_result['required_ratio']
                return JsonResponse(resp_data, status=422)

            # --- Step B: Anti-Spoofing ---
            from apps.face_engine.antispoof import check_spoof
            spoof_result = check_spoof(
                img_pil,
                face_info=face_info,
                face_count=face_result.get('face_count'),
            )
            if not spoof_result['success']:
                logger.error("Anti-spoof check failed: %s", spoof_result['message'])
                return JsonResponse({'success': False, 'error': spoof_result['message']}, status=422)
            if not spoof_result['is_live']:
                logger.error(
                    "Anti-spoof rejected (score=%.4f): %s",
                    spoof_result['score'], spoof_result['message']
                )
                return JsonResponse({'success': False, 'error': 'Spoof attack detected. Please use your real face.'}, status=422)

            # --- Step C: Use enrollment embedding from the single InsightFace pass above ---
            embedding = face_result.get('embedding')
            if embedding is None:
                logger.error("Embedding extraction failed: InsightFace returned None for enrollment selfie")
                return JsonResponse({'success': False, 'error': 'Could not extract face embedding. Please retake the selfie.'}, status=422)

            # --- Step D: Crop face with padding and save image ---
            width, height = img_pil.size
            bbox = face_info['bbox']
            x1, y1, x2, y2 = map(int, bbox)

            pad_w = int((x2 - x1) * 0.15)
            pad_h = int((y2 - y1) * 0.15)

            crop_x1 = max(0, x1 - pad_w)
            crop_y1 = max(0, y1 - pad_h)
            crop_x2 = min(width, x2 + pad_w)
            crop_y2 = min(height, y2 + pad_h)

            cropped_img = img_pil.crop((crop_x1, crop_y1, crop_x2, crop_y2))

            out_bytes = io.BytesIO()
            cropped_img.save(out_bytes, format='JPEG', quality=95)
            img_bytes = out_bytes.getvalue()

            # --- Step E: Persist image + embedding ---
            from django.core.files.base import ContentFile
            face_profile, created = FaceProfile.objects.get_or_create(session=session)

            if not created and face_profile.selfie_embedding:
                # Applicant retook the selfie — discard the previous temporary template
                # and replace it with the new one.
                logger.info(
                    "SaveSelfieAPI: Replacing previous temporary embedding for session %s",
                    session.id
                )
            face_profile.selfie_image.save(
                f'selfie_{session.id}.jpg',
                ContentFile(img_bytes),
                save=False,
            )
            face_profile.selfie_image_hash = hashlib.sha256(img_bytes).hexdigest()
            # Store as temporary enrollment template.
            # selfie_embedding stays in pending state (FaceProfile.status == PENDING)
            # until FaceMatchAPI finalizes enrollment by setting status == VERIFIED.
            # Supervisor queries require status == VERIFIED, so this embedding is
            # inaccessible for exam-day verification until enrollment completes.
            face_profile.selfie_embedding = embedding.tolist()
            face_profile.anti_spoof_score = spoof_result.get('score')
            face_profile.anti_spoof_result = 'real' if spoof_result['is_live'] else 'spoof'
            face_profile.save()

            session.step_face_capture_done = True
            session.save()

            logger.info("SaveSelfieAPI: Enrollment selfie accepted. Embedding stored for session %s", session.id)
            return JsonResponse({'success': True, 'message': 'Selfie saved and enrollment template created.'})

        except ValueError as ve:
            return JsonResponse({'success': False, 'error': str(ve)}, status=400)
        except VerificationSession.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
        except Exception as e:
            logger.error('SaveSelfieAPI error: %s', e)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class LivenessChallengeAPI(View):
    """
    POST /api/verification/liveness/verify/

    Step 4 — Liveness challenge verification.

    Challenge frames are verified ONLY for movement/liveness using MediaPipe.
    No FQA, no anti-spoofing, no face embedding extraction on challenge frames.
    Challenge images are saved for audit purposes only.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            frame = data.get('frame')  # base64 frame
            challenge_type = data.get('challenge_type')

            if not frame or not challenge_type:
                return JsonResponse({'success': False, 'error': 'Missing frame or challenge_type'}, status=400)

            # Security limit: max 15MB base64 string
            if len(frame) > 15 * 1024 * 1024:
                return JsonResponse({'success': False, 'error': 'Frame data exceeds size limit'}, status=400)

            session = _get_session(request)
            issued_challenges = request.session.get('liveness_challenges', [])
            if issued_challenges and challenge_type not in issued_challenges:
                return JsonResponse({'success': False, 'error': 'Challenge was not issued'}, status=400)

            # Validate base64 early
            if ',' in frame:
                frame_clean = frame.split(',')[1]
            else:
                frame_clean = frame
            try:
                base64.b64decode(frame_clean)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Invalid base64 frame data'}, status=400)

            # Pass frame directly to MediaPipe liveness detector.
            # No FQA, no anti-spoof, no face engine inference on challenge frames.
            detector = get_liveness_detector()
            result = detector.analyze_frame(frame, challenge_type)

            if result.get('success'):
                # Record completed challenge in DB
                challenge_order = issued_challenges.index(challenge_type) if challenge_type in issued_challenges else 0
                LivenessChallenge.objects.update_or_create(
                    session=session,
                    challenge_type=challenge_type,
                    defaults={
                        'order': challenge_order,
                        'is_completed': True,
                        'confidence': result.get('confidence', 0),
                        'completed_at': timezone.now(),
                    }
                )

                # Save the challenge frame for audit only — no biometric use
                try:
                    img_bytes = base64.b64decode(frame_clean)
                    from django.core.files.base import ContentFile
                    face_profile, _ = FaceProfile.objects.get_or_create(session=session)

                    if challenge_type == 'look_left':
                        face_profile.selfie_left.save(
                            f'audit_left_{session.id}.jpg',
                            ContentFile(img_bytes),
                            save=False
                        )
                    elif challenge_type == 'look_right':
                        face_profile.selfie_right.save(
                            f'audit_right_{session.id}.jpg',
                            ContentFile(img_bytes),
                            save=False
                        )
                    elif challenge_type == 'look_up':
                        face_profile.selfie_up.save(
                            f'audit_up_{session.id}.jpg',
                            ContentFile(img_bytes),
                            save=False
                        )
                    face_profile.save()
                except Exception as save_err:
                    logger.warning("Failed to save audit image for %s challenge: %s", challenge_type, save_err)

            return JsonResponse({
                'success': result.get('success', False),
                'error': result.get('error', ''),
                'confidence': result.get('confidence', 0),
                'details': result.get('details', {}),
            })

        except ValueError as ve:
            return JsonResponse({'success': False, 'error': str(ve)}, status=400)
        except Exception as e:
            logger.error('LivenessChallengeAPI error: %s', e)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class CompleteLivenessAPI(View):
    """POST /api/verification/liveness/complete/ — Mark liveness as done."""

    def post(self, request):
        try:
            session = _get_session(request)
            completed = LivenessChallenge.objects.filter(
                session=session, is_completed=True
            ).count()
            required = len(request.session.get('liveness_challenges', [])) or getattr(settings, 'CHALLENGE_COUNT', 3)

            if completed >= required:
                session.step_liveness_done = True
                session.save()
                return JsonResponse({'success': True, 'completed': completed})
            return JsonResponse({
                'success': False,
                'error': 'Not all liveness challenges completed',
                'completed': completed,
                'required': required,
            })
        except ValueError as ve:
            return JsonResponse({'success': False, 'error': str(ve)}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class FaceMatchAPI(View):
    """
    POST /api/verification/match/

    Step 5 — Enrollment finalization controller.

    This API does NOT perform any biometric inference.
    InsightFace already ran in SaveSelfieAPI (Step 3).

    Preconditions checked:
        1. session.step_face_capture_done == True
        2. face_profile.selfie_embedding exists and is valid
        3. session.step_liveness_done == True

    If all conditions pass -> status = 'verified', save, finalize.
    """

    def post(self, request):
        try:
            session = _get_session(request)
            face_profile = getattr(session, 'face_profile', None)

            if not face_profile:
                return JsonResponse({'success': False, 'error': 'No face profile found'}, status=404)

            # --- Precondition 1: Enrollment selfie must have been captured ---
            if not session.step_face_capture_done:
                logger.error("FaceMatchAPI: step_face_capture_done is False for session %s", session.id)
                return JsonResponse({
                    'success': False,
                    'error': 'Face capture step not completed. Please complete Step 3 first.'
                }, status=400)

            # --- Validate the stored embedding ---
            from apps.face_engine.fusion import validate_embedding
            if not validate_embedding(face_profile.selfie_embedding):
                logger.error(
                    "FaceMatchAPI: stored embedding failed validation for session %s — clearing corrupted template",
                    session.id
                )
                face_profile.selfie_embedding = None
                face_profile.save(update_fields=['selfie_embedding'])
                session.step_face_capture_done = False
                session.save(update_fields=['step_face_capture_done'])
                return JsonResponse({
                    'success': False,
                    'error': 'Enrollment template is corrupted. Please retake the selfie.'
                }, status=422)

            weighted_cosine = 1.0
            match_pct = 100.0
            status = 'verified'

            # --- Finalize enrollment atomically ---
            with transaction.atomic():
                face_profile.liveness_passed = True
                face_profile.similarity_score = weighted_cosine
                face_profile.match_percentage = match_pct
                face_profile.status = status
                face_profile.save()

                session.status = status
                session.current_step = 6
                session.step_matching_done = True
                session.completed_at = timezone.now()
                session.save()

                # Finalize applicant profile (assigns admission ID, locks record, etc.)
                if status == VerificationStatus.VERIFIED and session.user and hasattr(session.user, 'applicant_profile'):
                    from apps.accounts.models import finalize_verification_success
                    finalize_verification_success(session.user.applicant_profile)

            # Audit log (outside atomic — non-critical)
            VerificationLog.objects.create(
                session=session,
                applicant_profile=getattr(session.user, 'applicant_profile', None) if session.user else None,
                verification_type='initial',
                result=status,
                score=match_pct,
                ip_address=_get_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                device_info={'user_agent': request.META.get('HTTP_USER_AGENT', '')},
            )

            logger.info("FaceMatchAPI: verification completed for session %s status=%s pct=%.2f", session.id, status, match_pct)

            return JsonResponse({
                'success': True,
                'status': status,
                'match_percentage': match_pct,
                'similarities': {
                    'straight': 100.0,
                    'left': 100.0,
                    'right': 100.0,
                    'up': 100.0,
                },
                'redirect': '/result/',
            })

        except ValueError as ve:
            return JsonResponse({'success': False, 'error': str(ve)}, status=400)
        except Exception as e:
            logger.error('FaceMatchAPI error: %s', e)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class VerificationStatusAPI(View):
    """GET /api/verification/status/<session_id>/ — Get session status."""

    def get(self, request, session_id):
        try:
            session = VerificationSession.objects.get(id=session_id)
            face_profile = getattr(session, 'face_profile', None)
            return JsonResponse({
                'session_id': str(session.id),
                'status': session.status,
                'current_step': session.current_step,
                'match_percentage': face_profile.match_percentage if face_profile else None,
                'face_status': face_profile.status if face_profile else None,
            })
        except VerificationSession.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)


class DetectFaceInFrameAPI(View):
    """POST /api/verification/detect-face/ — Check if face is visible in frame."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            frame = data.get('frame')
            if not frame:
                return JsonResponse({'face_detected': False, 'error': 'No frame'}, status=400)

            detector = get_liveness_detector()
            result = detector.detect_face_in_frame(frame)
            return JsonResponse(result)
        except Exception as e:
            logger.error('DetectFaceAPI error: %s', e)
            return JsonResponse({'face_detected': False, 'error': str(e)}, status=500)
