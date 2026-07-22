from django.test import TransactionTestCase
from django.utils import timezone
from apps.accounts.models import CustomUser, ApplicantProfile, ExamVenueConfig, SystemSetting, finalize_verification_success
from apps.verification.models import VerificationSession, FaceProfile
from apps.qr_module.models import QRCode
from apps.qr_module.services import generate_applicant_qr
from apps.qr_module.exceptions import PermitNotReleasedError
from apps.reports.views import generate_confirmation_pdf_stream
import io

class QRAndPermitReleaseTestCase(TransactionTestCase):
    def setUp(self):
        # 1. Create a SystemSetting
        self.setting = SystemSetting.objects.create(
            qr_domain='id.akhu.uz',
            permits_released=False
        )

        # 2. Create an ExamVenueConfig
        self.venue_config = ExamVenueConfig.objects.create(
            region='Tashkent',
            venue_name='AKHU Main Campus Building A',
            arrival_time='2026-07-24 08:30',
            exam_date='2026-07-24 09:00'
        )

        # 3. Create a CustomUser and ApplicantProfile
        self.user = CustomUser.objects.create_user(
            username='candidate1',
            email='candidate1@test.com',
            password='password123',
            role='applicant'
        )
        self.profile = ApplicantProfile.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            passport_number='AA1234567',
            admission_id='TEMP-001',
            selected_region='Tashkent'
        )

        # 4. Create verified FaceProfile to simulate completed verification
        self.session = VerificationSession.objects.create(
            user=self.user,
            status='verified',
            current_step=6
        )
        self.face_profile = FaceProfile.objects.create(
            session=self.session,
            status='verified',
            match_percentage=98.5
        )

    def test_idempotent_qr_generation(self):
        """Test that calling generate_applicant_qr multiple times is idempotent."""
        qr1 = generate_applicant_qr(self.profile)
        self.assertIsNotNone(qr1)
        self.assertEqual(QRCode.objects.count(), 1)
        
        # Call again - should return the same object
        qr2 = generate_applicant_qr(self.profile)
        self.assertEqual(qr1.id, qr2.id)
        self.assertEqual(QRCode.objects.count(), 1)

    def test_permit_release_off_flow(self):
        """STEP 1: If Release Permits is OFF, finalize does not sync venue/date or generate QR."""
        finalize_verification_success(self.profile)
        
        # Profile must be finalized (locked & sequential ID assigned)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_locked)
        self.assertTrue(self.profile.admission_id.startswith('AKHU-2026-'))
        
        # But exam info & QR code must remain empty
        self.assertEqual(self.profile.exam_venue, "")
        self.assertEqual(self.profile.exam_date, "")
        self.assertEqual(self.profile.arrival_time, "")
        self.assertFalse(QRCode.objects.filter(applicant_profile=self.profile).exists())

    def test_permit_release_on_flow(self):
        """STEP 7: If Release Permits is ON, finalize immediately syncs venue/date and generates QR."""
        self.setting.permits_released = True
        self.setting.save()

        finalize_verification_success(self.profile)
        
        # Profile must be updated with regional venue/date & QR generated
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.exam_venue, self.venue_config.venue_name)
        self.assertEqual(self.profile.exam_date, self.venue_config.exam_date)
        self.assertEqual(self.profile.arrival_time, self.venue_config.arrival_time)
        self.assertTrue(QRCode.objects.filter(applicant_profile=self.profile).exists())

    def test_pdf_generation_without_qr_raises_error(self):
        """STEP 6: PDF generation must raise PermitNotReleasedError if QR code is missing."""
        buffer = io.BytesIO()
        with self.assertRaises(PermitNotReleasedError):
            generate_confirmation_pdf_stream(self.session, buffer)

    def test_admin_settings_release_permits(self):
        """Scenario 3: Admin enables Release Permits. All verified candidates receive venue/date & QR."""
        # 1. Finalize candidate under Release Permits = OFF
        finalize_verification_success(self.profile)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.exam_venue, "")
        self.assertEqual(self.profile.exam_date, "")
        self.assertEqual(self.profile.arrival_time, "")
        self.assertFalse(QRCode.objects.filter(applicant_profile=self.profile).exists())

        # 2. Simulate logged-in admin session
        session = self.client.session
        from apps.admin_panel.views import ADMIN_SESSION_KEY
        session[ADMIN_SESSION_KEY] = True
        session.save()

        # 3. POST to settings view to turn ON permits_released
        from django.urls import reverse
        url = reverse('admin_panel:settings')
        response = self.client.post(url, {
            'qr_domain': 'id.akhu.uz',
            'permits_released': 'on',
            f'region_name_{self.venue_config.id}': self.venue_config.region,
            f'venue_{self.venue_config.id}': self.venue_config.venue_name,
            f'arrival_{self.venue_config.id}': self.venue_config.arrival_time,
            f'date_{self.venue_config.id}': self.venue_config.exam_date,
        })
        self.assertEqual(response.status_code, 302)  # redirects to settings page
        
        # 4. Check that candidate profile was synchronized and QR generated
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.exam_venue, self.venue_config.venue_name)
        self.assertEqual(self.profile.exam_date, self.venue_config.exam_date)
        self.assertEqual(self.profile.arrival_time, self.venue_config.arrival_time)
        self.assertTrue(QRCode.objects.filter(applicant_profile=self.profile).exists())
