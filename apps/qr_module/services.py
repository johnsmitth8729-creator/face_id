"""
AKHU AFIVS — QR Code Services
Dedicated service to manage candidate QR code generation.
"""
import io
import logging
from pathlib import Path
from datetime import timedelta

import qrcode
from PIL import Image
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.core.files.base import ContentFile

from apps.qr_module.models import QRCode
from apps.qr_module.generator import _generate_token, _sign_token

logger = logging.getLogger(__name__)

def generate_applicant_qr(applicant_profile, force=False) -> QRCode:
    """
    Generate a QR code for a verified applicant.
    This is the single source of truth for QR code generation.
    Returns the created/existing QRCode model instance.
    """
    # Check if QR already exists
    existing = QRCode.objects.filter(applicant_profile=applicant_profile).first()
    if existing and not force:
        return existing

    # If force=True and existing QR exists, delete it first to regenerate
    if existing and force:
        existing.delete()

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
            continue

    raise IntegrityError("Failed to generate unique QR code token after 10 attempts")
