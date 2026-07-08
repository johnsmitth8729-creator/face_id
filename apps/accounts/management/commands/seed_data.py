import sys
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import CustomUser, ApplicantProfile, SupervisorAccount, UserRole
from apps.verification.models import (
    VerificationSession, FaceProfile, VerificationLog,
    VerificationStatus, VerificationType, VerificationStep
)
from apps.qr_module.models import QRCode
from apps.qr_module.generator import generate_qr_code


class Command(BaseCommand):
    help = 'Seed the database with initial testing data (supervisors and applicants)'

    def handle(self, *args, **options):
        # 1. Create a default supervisor
        sup_username = 'supervisor'
        sup_password = 'Supervisor@AKHU2026!'
        sup_fullname = 'Sherzod Alimov'

        # Delete existing to prevent unique constraints or duplication
        CustomUser.objects.filter(username=sup_username).delete()

        admin_user = CustomUser.objects.filter(role=UserRole.ADMIN).first()
        user = CustomUser.objects.create_supervisor(
            username=sup_username,
            password=sup_password,
            created_by=admin_user,
        )
        
        # Update details on the automatically created SupervisorAccount
        sa = user.supervisor_account
        sa.full_name = sup_fullname
        sa.notes = 'Default test supervisor for AFIVS verification'
        sa.save()
        
        self.stdout.write(self.style.SUCCESS(f"Supervisor '{sup_username}' created successfully."))

        # 2. Seed Applicant 1: Verified
        self.seed_applicant(
            admission_id='AKHU-2026-0001',
            passport_number='AA1111111',
            first_name='Abduvali',
            last_name='Karimov',
            email='abduvali@gmail.com',
            status=VerificationStatus.VERIFIED,
            pct=94.5,
        )

        # 3. Seed Applicant 2: Review Required (Pending Admin Review)
        self.seed_applicant(
            admission_id='AKHU-2026-0002',
            passport_number='AA2222222',
            first_name='Malika',
            last_name='Salieva',
            email='malika@gmail.com',
            status=VerificationStatus.REVIEW_REQUIRED,
            pct=84.2,
        )

        # 4. Seed Applicant 3: Rejected (Mismatch)
        self.seed_applicant(
            admission_id='AKHU-2026-0003',
            passport_number='AA3333333',
            first_name='John',
            last_name='Doe',
            email='johndoe@example.com',
            status=VerificationStatus.REJECTED,
            pct=42.1,
        )

        self.stdout.write(self.style.SUCCESS('Database seeding completed.'))

    def seed_applicant(self, admission_id, passport_number, first_name, last_name, email, status, pct):
        # Clean old if exists
        ApplicantProfile.objects.filter(admission_id=admission_id).delete()

        # Create user
        username = f'applicant_{admission_id.replace("-", "_").lower()}'
        CustomUser.objects.filter(username=username).delete()

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            role=UserRole.APPLICANT,
        )

        # Create Profile
        profile = ApplicantProfile.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            middle_name='Test',
            date_of_birth=datetime.date(2003, 5, 15),
            passport_number=passport_number,
            admission_id=admission_id,
            phone_number='+998901234567',
            email=email,
            is_locked=(status == VerificationStatus.VERIFIED),
        )

        # Create Verification Session
        session = VerificationSession.objects.create(
            user=user,
            current_step=VerificationStep.COMPLETED,
            status=status,
            verification_type=VerificationType.INITIAL,
            step_personal_info_done=True,
            step_document_done=True,
            step_face_capture_done=True,
            step_liveness_done=True,
            step_matching_done=True,
            completed_at=timezone.now(),
        )

        # Create Face Profile
        face_profile = FaceProfile.objects.create(
            session=session,
            similarity_score=(pct / 100.0),
            match_percentage=pct,
            status=status,
            liveness_passed=True,
            anti_spoof_result='real',
            anti_spoof_score=0.95,
        )

        # Generate QR Code if Verified
        if status == VerificationStatus.VERIFIED:
            generate_qr_code(profile)

        # Create Verification Log
        VerificationLog.objects.create(
            session=session,
            applicant_profile=profile,
            verification_type=VerificationType.INITIAL,
            result=status,
            score=pct,
            ip_address='127.0.0.1',
            notes='Seeded mock verification data',
        )

        self.stdout.write(self.style.SUCCESS(f"Seeded applicant {first_name} {last_name} ({admission_id}) with status '{status}'."))
