import sys
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.accounts.models import CustomUser, UserRole


class Command(BaseCommand):
    help = 'Create an administrative superuser in the database'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Admin username')
        parser.add_argument('--email', type=str, help='Admin email')
        parser.add_argument('--password', type=str, help='Admin password')
        parser.add_argument('--no-input', action='store_true', help='Do not prompt for inputs')

    def handle(self, *args, **options):
        username = options.get('username') or settings.ADMIN_USERNAME
        email = options.get('email') or getattr(settings, 'ADMIN_EMAIL', 'admin@akhu.uz')
        password = options.get('password') or settings.ADMIN_PASSWORD

        if not username or not password:
            self.stdout.write(self.style.ERROR('Username and password are required.'))
            sys.exit(1)

        # Check if user already exists
        if CustomUser.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"User '{username}' already exists. Updating password..."))
            user = CustomUser.objects.get(username=username)
            user.set_password(password)
            user.email = email
            user.role = UserRole.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"User '{username}' updated successfully."))
            return

        # Create new superuser
        try:
            user = CustomUser.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            self.stdout.write(self.style.SUCCESS(f"Admin user '{username}' created successfully."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creating admin user: {e}"))
            sys.exit(1)
