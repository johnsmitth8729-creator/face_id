"""
AKHU AFIVS — Accounts Models
CustomUser, ApplicantProfile, SupervisorAccount
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class UserRole(models.TextChoices):
    APPLICANT = 'applicant', _('Applicant')
    SUPERVISOR = 'supervisor', _('Supervisor')
    ADMIN = 'admin', _('Administrator')


class CustomUserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError(_('Username is required'))
        email = self.normalize_email(email) if email else ''
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.ADMIN)
        return self.create_user(username, email, password, **extra_fields)

    def create_supervisor(self, username, password, created_by=None, **extra_fields):
        extra_fields['role'] = UserRole.SUPERVISOR
        extra_fields['is_staff'] = False
        extra_fields['is_superuser'] = False
        user = self.create_user(username, **extra_fields, password=password)
        if created_by:
            SupervisorAccount.objects.create(user=user, created_by=created_by)
        return user


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Core user model for all roles."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(_('username'), max_length=150, unique=True)
    email = models.EmailField(_('email address'), blank=True, null=True)
    role = models.CharField(
        _('role'),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.APPLICANT,
    )
    is_active = models.BooleanField(_('active'), default=True)
    is_staff = models.BooleanField(_('staff status'), default=False)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

    @property
    def is_applicant(self):
        return self.role == UserRole.APPLICANT

    @property
    def is_supervisor(self):
        return self.role == UserRole.SUPERVISOR

    @property
    def is_admin_user(self):
        return self.role == UserRole.ADMIN


class ApplicantProfile(models.Model):
    """Personal information submitted by applicants (Step 2)."""
    GENDER_CHOICES = [
        ('M', _('Male')),
        ('F', _('Female')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='applicant_profile',
    )

    # Personal Info
    first_name = models.CharField(_('First Name'), max_length=100)
    last_name = models.CharField(_('Last Name'), max_length=100)
    middle_name = models.CharField(_('Middle Name'), max_length=100, blank=True)
    date_of_birth = models.DateField(_('Date of Birth'), null=True, blank=True)
    gender = models.CharField(_('Gender'), max_length=1, choices=GENDER_CHOICES, blank=True)

    # Contact
    phone_number = models.CharField(_('Phone Number'), max_length=20, blank=True)
    email = models.EmailField(_('Email Address'), blank=True)

    # Identification
    passport_number = models.CharField(_('Passport Number'), max_length=50, unique=True)
    admission_id = models.CharField(_('Admission ID'), max_length=100, unique=True)

    # Custom/Excel columns
    applicant_id = models.CharField(_('Applicant ID'), max_length=100, blank=True, null=True)
    program = models.CharField(_('Program'), max_length=200, blank=True)
    selected_region = models.CharField(_('Selected Region'), max_length=100, blank=True)
    exam_venue = models.CharField(_('Exam Venue'), max_length=500, blank=True)
    exam_date = models.DateTimeField(_('Exam Date & Time'), null=True, blank=True)
    passport_image = models.ImageField(_('Passport / ID Image'), upload_to='passports/%Y/%m/', null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_locked = models.BooleanField(
        _('Locked'),
        default=False,
        help_text=_('Profile is locked after verification approval'),
    )

    class Meta:
        verbose_name = _('Applicant Profile')
        verbose_name_plural = _('Applicant Profiles')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.last_name} {self.first_name} — {self.admission_id}'

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return ' '.join(parts)


class SupervisorAccount(models.Model):
    """Supervisor-specific metadata."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='supervisor_account',
    )
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_supervisors',
    )
    full_name = models.CharField(_('Full Name'), max_length=200)
    notes = models.TextField(_('Notes'), blank=True)
    is_active = models.BooleanField(_('Active'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Supervisor Account')
        verbose_name_plural = _('Supervisor Accounts')
        ordering = ['-created_at']

    def __str__(self):
        return f'Supervisor: {self.full_name} ({self.user.username})'


class PreRegisteredApplicant(models.Model):
    """Allowed applicants uploaded by Admin via Excel."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant_id = models.CharField(_('Applicant ID'), max_length=100, unique=True, null=True, blank=True)
    surname = models.CharField(_('Surname'), max_length=100, default="")
    given_name = models.CharField(_('Given Name'), max_length=100, default="")
    middle_name = models.CharField(_('Middle Name'), max_length=100, blank=True)
    program = models.CharField(_('Program'), max_length=200, blank=True)
    region = models.CharField(_('Region'), max_length=100, blank=True)
    passport_number = models.CharField(_('Card / Passport Number'), max_length=50, unique=True)
    passport_image = models.ImageField(upload_to='passports/%Y/%m/', null=True, blank=True)
    passport_embedding = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Pre-Registered Applicant')
        verbose_name_plural = _('Pre-Registered Applicants')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.surname} {self.given_name} — {self.passport_number}'


def check_permit_ready() -> bool:
    """Helper to check if permits have been officially released by admin settings."""
    setting = SystemSetting.objects.first()
    return bool(setting and setting.permits_released)


def _generate_qr_post_commit(profile_id):
    """Helper to generate QR code after transaction commit."""
    from apps.accounts.models import ApplicantProfile
    from apps.qr_module.services import generate_applicant_qr
    try:
        profile = ApplicantProfile.objects.get(id=profile_id)
        generate_applicant_qr(profile)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to generate QR code in on_commit for applicant {profile_id}: {e}")


def finalize_verification_success(profile):
    """Finalizes an applicant's profile upon successful verification:
       1. Generates a sequential Admission ID.
       2. Locks the profile.
       3. Removes them from the PreRegisteredApplicant list.
    """
    import re
    from django.db import transaction

    with transaction.atomic():
        # Lock ALL matching rows to prevent concurrent assignment of the same sequential ID.
        # select_for_update ensures no two concurrent transactions can both read the same max.
        existing = ApplicantProfile.objects.filter(
            admission_id__startswith='AKHU-2026-'
        ).exclude(
            admission_id__startswith='TEMP-'
        ).select_for_update()

        max_num = 0
        for ap in existing:
            m = re.search(r'AKHU-2026-(\d+)', ap.admission_id)
            if m:
                max_num = max(max_num, int(m.group(1)))

        next_id = f'AKHU-2026-{max_num + 1:04d}'

        # Look up regional exam configs ONLY if permits are ready
        if check_permit_ready():
            if profile.selected_region:
                try:
                    venue_conf = ExamVenueConfig.objects.get(region=profile.selected_region)
                    profile.exam_venue = venue_conf.venue_name
                    profile.exam_date = venue_conf.exam_date
                except ExamVenueConfig.DoesNotExist:
                    pass
        else:
            profile.exam_venue = ""
            profile.exam_date = None

        profile.admission_id = next_id
        profile.is_locked = True
        profile.save()

        # Remove from PreRegisteredApplicant list
        PreRegisteredApplicant.objects.filter(passport_number=profile.passport_number).delete()

        # Post-commit QR generation if permits are ready
        if check_permit_ready():
            transaction.on_commit(lambda: _generate_qr_post_commit(profile.id))



class SystemSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_domain = models.CharField(_('QR Code Domain'), max_length=255, default='id.akhu.uz')
    permits_released = models.BooleanField(_('Permits Released'), default=False)
    permit_release_date = models.DateField(_('Permit Release Date'), null=True, blank=True)

    class Meta:
        verbose_name = _('System Setting')
        verbose_name_plural = _('System Settings')

    def __str__(self):
        return f"Settings — Domain: {self.qr_domain}, Released: {self.permits_released}"


class ExamVenueConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    region = models.CharField(_('Region'), max_length=100, unique=True)
    venue_name = models.CharField(_('Venue Name'), max_length=500, blank=True)
    exam_date = models.DateTimeField(_('Exam Date & Time'), null=True, blank=True)
    location_link = models.CharField(_('Location Link'), max_length=1000, blank=True)

    class Meta:
        verbose_name = _('Exam Venue Config')
        verbose_name_plural = _('Exam Venue Configs')

    def __str__(self):
        return f"{self.region} — {self.venue_name or 'No Venue'}"
