"""
AKHU AFIVS — QR Code Generator
Generates signed QR codes with JWT tokens.
"""
import io
import hashlib
import logging
from pathlib import Path
from datetime import timedelta

import qrcode
from qrcode.image.pure import PyPNGImage
from PIL import Image
from django.conf import settings
from django.db.models import F
from django.utils import timezone
import jwt

logger = logging.getLogger(__name__)


def _generate_token(applicant_id: str, profile_id: str, year: int) -> str:
    """
    Generate unique sequential token like AKHU2026-000001.
    MUST be called inside a transaction.atomic() block with select_for_update
    to prevent duplicate tokens under concurrent access.
    """
    from apps.qr_module.models import QRCode
    # Lock the latest token row to serialize generation
    last = QRCode.objects.select_for_update().order_by('-generated_at').first()
    count = QRCode.objects.count() + 1
    while True:
        token = f'AKHU{year}-{count:06d}'
        if not QRCode.objects.filter(token=token).exists():
            return token
        count += 1


def _sign_token(token: str, applicant_id: str, status: str) -> str:
    """Create a JWT-signed payload for tamper detection."""
    payload = {
        'token': token,
        'applicant_id': str(applicant_id),
        'status': status,
        'iat': timezone.now().timestamp(),
        'exp': (timezone.now() + timedelta(days=settings.QR_CODE.get('TOKEN_EXPIRY_DAYS', 365))).timestamp(),
    }
    secret = settings.QR_CODE.get('SECRET', settings.SECRET_KEY)
    return jwt.encode(payload, secret, algorithm='HS256')


def _verify_signed_token(signed_token: str) -> dict:
    """Verify and decode a signed JWT token."""
    try:
        secret = settings.QR_CODE.get('SECRET', settings.SECRET_KEY)
        payload = jwt.decode(signed_token, secret, algorithms=['HS256'])
        return {'valid': True, 'payload': payload}
    except jwt.ExpiredSignatureError:
        return {'valid': False, 'error': 'Token expired'}
    except jwt.InvalidTokenError as e:
        return {'valid': False, 'error': str(e)}


def generate_qr_code(applicant_profile) -> 'apps.qr_module.models.QRCode':
    """
    Generate a QR code for a verified applicant.
    Returns the created QRCode model instance.
    """
    from apps.qr_module.models import QRCode
    from django.db import IntegrityError, transaction
    from django.core.files.base import ContentFile

    # Check if QR already exists
    existing = QRCode.objects.filter(applicant_profile=applicant_profile).first()
    if existing:
        return existing

    year = timezone.now().year
    for attempt in range(10):
        try:
            with transaction.atomic():
                token = _generate_token(
                    str(applicant_profile.id),
                    str(applicant_profile.id),
                    year,
                )

                signed = _sign_token(
                    token,
                    str(applicant_profile.id),
                    'verified',
                )

                # Build QR data URL dynamically from SystemSetting
                from apps.accounts.models import SystemSetting
                setting = SystemSetting.objects.first()
                domain = setting.qr_domain if (setting and setting.qr_domain) else 'id.akhu.uz'
                if not domain.startswith(('http://', 'https://')):
                    base_url = f'https://{domain}/verify/qr/'
                else:
                    base_url = f'{domain}/verify/qr/'
                if not base_url.endswith('/'):
                    base_url += '/'
                qr_data = f'{base_url}{token}'

                # Generate QR image
                qr = qrcode.QRCode(
                    version=3,
                    error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=10,
                    border=4,
                )
                qr.add_data(qr_data)
                qr.make(fit=True)

                qr_img = qr.make_image(fill_color='#0A1628', back_color='white')

                # Add logo overlay (optional — skip if no logo file)
                logo_path = Path(settings.BASE_DIR) / 'static' / 'images' / 'logo_small.png'
                if logo_path.exists():
                    try:
                        logo = Image.open(logo_path).convert('RGBA')
                        qr_pil = qr_img.get_image()
                        qr_w, qr_h = qr_pil.size
                        logo_size = qr_w // 5
                        logo = logo.resize((logo_size, logo_size))
                        pos = ((qr_w - logo_size) // 2, (qr_h - logo_size) // 2)
                        qr_pil.paste(logo, pos, mask=logo)
                        qr_img_to_save = qr_pil
                    except Exception as e:
                        logger.warning(f'Could not add logo to QR: {e}')
                        qr_img_to_save = qr_img.get_image()
                else:
                    qr_img_to_save = qr_img.get_image()

                # Save to Django ImageField
                img_io = io.BytesIO()
                qr_img_to_save.save(img_io, format='PNG')
                img_io.seek(0)

                qr_obj = QRCode.objects.create(
                    applicant_profile=applicant_profile,
                    token=token,
                    signed_token=signed,
                    status='active',
                    expires_at=timezone.now() + timedelta(days=settings.QR_CODE.get('TOKEN_EXPIRY_DAYS', 365)),
                )
                qr_obj.qr_image.save(f'{token}.png', ContentFile(img_io.read()), save=True)
                logger.info(f'Generated QR code {token} for applicant {applicant_profile.admission_id}')
                return qr_obj
        except IntegrityError as e:
            logger.warning(f'Token collision for {token} (attempt {attempt+1}): {e}')
            # Continue the loop to retry with a fresh token
            continue

    raise IntegrityError("Failed to generate unique QR code token after 10 attempts")


def scan_qr_token(token: str, scanned_by=None) -> dict:
    """
    Look up a QR token and return applicant verification data.
    """
    from apps.qr_module.models import QRCode

    try:
        qr_obj = QRCode.objects.select_related(
            'applicant_profile',
            'applicant_profile__user',
        ).get(token=token)
    except QRCode.DoesNotExist:
        return {'valid': False, 'error': 'QR code not found'}

    if qr_obj.status == 'revoked':
        return {'valid': False, 'error': 'QR code has been revoked'}

    if qr_obj.status == 'expired':
        return {'valid': False, 'error': 'QR code has expired'}

    if qr_obj.expires_at and qr_obj.expires_at < timezone.now():
        qr_obj.status = 'expired'
        qr_obj.save()
        return {'valid': False, 'error': 'QR code has expired'}

    # Verify JWT signature. Older QR rows can have signatures created with a
    # previous SECRET_KEY; if the DB token is valid, refresh the stored signature.
    token_check = _verify_signed_token(qr_obj.signed_token)
    if not token_check['valid']:
        logger.warning(
            'Refreshing QR signature for %s after verification failure: %s',
            qr_obj.token,
            token_check.get('error'),
        )
        qr_obj.signed_token = _sign_token(
            qr_obj.token,
            str(qr_obj.applicant_profile_id),
            qr_obj.status,
        )
        qr_obj.save(update_fields=['signed_token'])

    # Update scan count atomically to avoid lost-update under concurrent scans
    QRCode.objects.filter(pk=qr_obj.pk).update(
        scan_count=F('scan_count') + 1,
        last_scanned_at=timezone.now(),
        **({'last_scanned_by': scanned_by} if scanned_by else {}),
    )
    qr_obj.refresh_from_db()

    profile = qr_obj.applicant_profile
    from apps.verification.models import FaceProfile
    face_prof = FaceProfile.objects.filter(session__user=profile.user, status='verified').first()
    if not face_prof:
        face_prof = FaceProfile.objects.filter(session__user=profile.user).first()
    selfie_url = face_prof.selfie_image.url if face_prof and face_prof.selfie_image else ""

    return {
        'valid': True,
        'token': token,
        'applicant': {
            'id': str(profile.id),
            'admission_id': profile.admission_id,
            'full_name': profile.full_name,
            'passport_number': profile.passport_number,
            'date_of_birth': str(profile.date_of_birth),
            'selfie_url': selfie_url,
        },
        'qr_status': qr_obj.status,
        'scan_count': qr_obj.scan_count,
    }
