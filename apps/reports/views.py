"""AKHU AFIVS — Reports views + PDF download endpoints"""
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from apps.reports.exporters import (
    export_csv, export_excel, export_pdf,
    get_verified_applicants_data, get_failed_verifications_data,
    get_supervisor_activity_data, get_attendance_report_data,
    get_pre_registered_data, get_audit_logs_data, get_daily_stats_data
)
from apps.admin_panel.views import ADMIN_SESSION_KEY


REPORT_BUILDERS = {
    'verified': get_verified_applicants_data,
    'failed': get_failed_verifications_data,
    'supervisor_activity': get_supervisor_activity_data,
    'attendance': get_attendance_report_data,
    'pre_registered': get_pre_registered_data,
    'audit_logs': get_audit_logs_data,
    'daily_stats': get_daily_stats_data,
}


class ExportReportView(View):
    """GET /reports/export/<report_type>/<format>/ — Export report."""

    def get(self, request, report_type, fmt):
        if not request.session.get(ADMIN_SESSION_KEY):
            return redirect(settings.ADMIN_PANEL_LOGIN_URL)

        builder = REPORT_BUILDERS.get(report_type)
        if not builder:
            return HttpResponse('Unknown report type', status=404)

        try:
            headers, data = builder()
            from apps.reports.exporters import _get_report_title
            title = _get_report_title(report_type)
            filename = f'akhu_{report_type}_{__import__("datetime").datetime.now().strftime("%Y%m%d_%H%M")}'

            if fmt == 'csv':
                return export_csv(data, headers, filename)
            elif fmt == 'excel':
                return export_excel(data, headers, title, filename)
            elif fmt == 'pdf':
                return export_pdf(data, headers, title, filename)
            else:
                return HttpResponse('Invalid format', status=400)

        except Exception as e:
            return HttpResponse(f'Export error: {e}', status=500)


def generate_confirmation_pdf_stream(session, stream) -> bool:
    """Generate a beautifully designed PDF admission permit directly to a file-like stream."""
    import os
    from django.conf import settings
    from django.utils import timezone
    from apps.verification.models import FaceProfile
    
    # 1. Resolve face profile fallback
    face_profile = getattr(session, 'face_profile', None)
    if not face_profile and session.user:
        face_profile = FaceProfile.objects.filter(
            session__user=session.user,
            status='verified'
        ).first()
        
    applicant = getattr(session.user, 'applicant_profile', None) if session.user else None

    if not face_profile or not applicant:
        return False

    # 2. Setup PDF document
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, HRFlowable
        from PIL import Image as PILImage
    except ImportError:
        return False

    def get_scaled_reportlab_image(image_path, max_w, max_h):
        try:
            with PILImage.open(image_path) as img:
                w, h = img.size
            ratio = min(max_w / w, max_h / h)
            new_w = w * ratio
            new_h = h * ratio
            return Image(image_path, width=new_w, height=new_h)
        except Exception:
            return Image(image_path, width=max_w, height=max_h)

    doc = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    # 3. Design System colors & styles
    AKHU_NAVY = colors.HexColor('#0A1628')
    AKHU_GOLD = colors.HexColor('#F59E0B')
    TEXT_DARK = colors.HexColor('#1E293B')
    TEXT_MUTED = colors.HexColor('#64748B')
    BG_LIGHT = colors.HexColor('#F8FAFC')
    BORDER_LIGHT = colors.HexColor('#E2E8F0')

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Title'],
        fontName='Helvetica-Bold', fontSize=18, textColor=AKHU_NAVY,
        alignment=TA_RIGHT, spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        'DocSub', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=10, textColor=AKHU_GOLD,
        alignment=TA_RIGHT, spaceAfter=2
    )
    system_text_style = ParagraphStyle(
        'SysText', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, textColor=TEXT_MUTED,
        alignment=TA_RIGHT
    )

    label_style = ParagraphStyle(
        'LabelCol', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=10, textColor=AKHU_NAVY,
        leading=13
    )
    value_style = ParagraphStyle(
        'ValueCol', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, textColor=TEXT_DARK,
        leading=13
    )

    instructions_title = ParagraphStyle(
        'InstTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=11, textColor=AKHU_NAVY,
        spaceAfter=6
    )
    instructions_text = ParagraphStyle(
        'InstText', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, textColor=TEXT_DARK,
        leading=12
    )

    elements = []

    # 4. Header: Logo & Title Table
    # Logo Path
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo-dark.png')
    logo_img = None
    if os.path.exists(logo_path):
        logo_img = get_scaled_reportlab_image(logo_path, 220, 70)
    
    # Right Header Info
    header_info = [
        Paragraph("<b>ADMISSION PERMIT</b>", title_style),
        Paragraph("<b>AL-KHWARIZMI UNIVERSITY</b>", subtitle_style),
        Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}", system_text_style),
    ]

    header_table_data = [
        [logo_img or "", header_info]
    ]
    # Header widths: 220 points for Logo, 290 points for title
    header_table = Table(header_table_data, colWidths=[220, 290])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, 0), 15),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.4 * cm))

    # Divider line
    elements.append(HRFlowable(width='100%', thickness=2, color=AKHU_NAVY, spaceAfter=15))

    # 5. Core Layout columns (Left: Photo + QR, Right: Candidate details)
    # Get Photo (Selfie fallback to Passport)
    photo_img = None
    for attr in ('selfie_image',):
        img_field = getattr(face_profile, attr, None)
        if img_field:
            try:
                p = img_field.path
                if os.path.exists(p):
                    photo_img = get_scaled_reportlab_image(p, 112, 140)
                    break
            except Exception:
                pass

    # If no photo, build a placeholder cell
    if not photo_img:
        placeholder_data = [[Paragraph("<b>NO PHOTO<br/>AVAILABLE</b>", ParagraphStyle('NoPhoto', parent=styles['Normal'], alignment=TA_CENTER, fontName='Helvetica-Bold', fontSize=10, textColor=TEXT_MUTED))]]
        photo_img = Table(placeholder_data, colWidths=[112], rowHeights=[140])
        photo_img.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 1, BORDER_LIGHT),
        ]))

    # Get QR image
    qr_img = None
    qr = getattr(applicant, 'qr_code', None)
    if not qr or not qr.qr_image:
        from apps.qr_module.exceptions import PermitNotReleasedError
        raise PermitNotReleasedError(f"QR code does not exist for applicant {applicant.admission_id if applicant else 'unknown'}")

    try:
        p = qr.qr_image.path
        if not os.path.exists(p):
            raise FileNotFoundError(f"QR code image file not found at {p}")
        qr_img = get_scaled_reportlab_image(p, 96, 96)
    except Exception as e:
        raise e

    # Left column content
    left_flowables = [
        photo_img,
        Spacer(1, 0.4 * cm),
    ]
    if qr_img:
        left_flowables.extend([
            qr_img,
            Spacer(1, 0.1 * cm),
            Paragraph(f"<b>Token: {qr.token}</b>", ParagraphStyle('QrToken', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8, textColor=AKHU_GOLD)),
            Paragraph("Scan to check-in at entrance", ParagraphStyle('QrScan', parent=styles['Normal'], alignment=TA_CENTER, fontSize=7, textColor=TEXT_MUTED))
        ])

    left_column_table = Table([[f] for f in left_flowables], colWidths=[120])
    left_column_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    # Right column details table
    exam_date_str = "—"
    if applicant.exam_date:
        exam_date_str = applicant.exam_date.strftime('%Y-%m-%d %H:%M')

    details_data = [
        [Paragraph("Applicant ID", label_style), Paragraph(applicant.applicant_id or "—", value_style)],
        [Paragraph("Surname", label_style), Paragraph(applicant.last_name, value_style)],
        [Paragraph("Given Name", label_style), Paragraph(applicant.first_name, value_style)],
        [Paragraph("Middle Name", label_style), Paragraph(applicant.middle_name or "—", value_style)],
        [Paragraph("Passport / Card Number", label_style), Paragraph(applicant.passport_number, value_style)],
        [Paragraph("Academic Program", label_style), Paragraph(applicant.program or "—", value_style)],
        [Paragraph("Exam Region", label_style), Paragraph(applicant.selected_region or "—", value_style)],
        [Paragraph("Exam Venue", label_style), Paragraph(applicant.exam_venue or "—", value_style)],
        [Paragraph("Exam Date & Time", label_style), Paragraph(exam_date_str, value_style)],
        [Paragraph("Biometric Match Score", label_style), Paragraph(f"{face_profile.match_percentage:.1f}% Verified" if face_profile.match_percentage else "Verified", value_style)],
    ]
    
    details_table = Table(details_data, colWidths=[150, 220])
    details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, BORDER_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_LIGHT),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))

    # Combine left and right columns
    main_layout_table = Table([[left_column_table, "", details_table]], colWidths=[125, 15, 370])
    main_layout_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(main_layout_table)
    elements.append(Spacer(1, 0.6 * cm))

    # 6. Instructions Box
    instructions_box_data = [
        [
            [
                Paragraph("<b>IMPORTANT INSTRUCTIONS FOR CANDIDATES</b>", instructions_title),
                Paragraph(
                    "1. <b>Identity Documents:</b> Candidates must present this Admission Permit along with their original Passport or ID Card at the entrance.<br/>"
                    "2. <b>Arrival Time:</b> Arrive at the examination venue at least 30 minutes before the scheduled exam start time. Late arrivals will not be admitted.<br/>"
                    "3. <b>Biometric Verification:</b> Your identity will be verified at the entrance using the printed QR code and the live Face ID verification system. Ensure your face is fully visible.<br/>"
                    "4. <b>Prohibited Items:</b> Mobile phones, smartwatches, calculators, bags, and any written/printed materials are strictly prohibited inside the exam hall.<br/>"
                    "5. <b>Exam Venue:</b> Confirm your venue address carefully. This permit is valid only for the specific venue, date, and time printed above.",
                    instructions_text
                )
            ]
        ]
    ]
    
    instructions_table = Table(instructions_box_data, colWidths=[510])
    instructions_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FEF3C7')), # Light gold background
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#F59E0B')), # Gold border
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(instructions_table)

    # 6.5. Bottom center Google Maps location QR code
    location_qr_table = None
    if applicant.selected_region:
        try:
            from apps.accounts.models import ExamVenueConfig
            venue_conf = ExamVenueConfig.objects.filter(region=applicant.selected_region).first()
            if venue_conf and venue_conf.location_link:
                import qrcode
                from reportlab.platypus import Image as RLImage
                import io
                
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=1,
                )
                qr.add_data(venue_conf.location_link)
                qr.make(fit=True)
                qr_img_pil = qr.make_image(fill_color='black', back_color='white')
                
                qr_io = io.BytesIO()
                qr_img_pil.save(qr_io, format='PNG')
                qr_io.seek(0)
                
                location_qr_img = RLImage(qr_io, width=1.8*cm, height=1.8*cm)
                
                location_text_style = ParagraphStyle(
                    'LocText', parent=styles['Normal'],
                    fontName='Helvetica-Bold', fontSize=8, textColor=AKHU_NAVY,
                    alignment=TA_CENTER, spaceBefore=4
                )
                
                location_flowables = [
                    location_qr_img,
                    Paragraph("Scan to view exam location", location_text_style)
                ]
                
                location_qr_table = Table([[f] for f in location_flowables], colWidths=[200])
                location_qr_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]))
        except Exception as e:
            logger.warning(f"Failed to generate location QR: {e}")

    if location_qr_table:
        elements.append(Spacer(1, 0.4 * cm))
        elements.append(location_qr_table)

    # 7. Build Document
    doc.build(elements)
    return True


def generate_confirmation_pdf(session) -> HttpResponse:
    """Generate a beautifully designed PDF admission permit with photo, QR and logo."""
    import io
    from apps.qr_module.exceptions import PermitNotReleasedError
    buffer = io.BytesIO()
    try:
        success = generate_confirmation_pdf_stream(session, buffer)
        if not success:
            return HttpResponse('No data available', status=404)
    except PermitNotReleasedError as e:
        return HttpResponse(str(e), status=403)
    except Exception as e:
        return HttpResponse(f'Error generating PDF: {e}', status=500)

    applicant = getattr(session.user, 'applicant_profile', None) if session.user else None
    passport = applicant.passport_number if applicant else 'unknown'

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="permit_{passport}.pdf"'
    response.write(buffer.getvalue())
    buffer.close()
    return response
