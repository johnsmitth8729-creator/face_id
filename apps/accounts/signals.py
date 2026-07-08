"""AKHU AFIVS — Accounts signals"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='accounts.CustomUser')
def user_post_save(sender, instance, created, **kwargs):
    if created:
        from apps.audit.models import AuditLog
        try:
            AuditLog.objects.create(
                user=instance,
                username_snapshot=instance.username,
                user_role_snapshot=instance.role,
                category='auth',
                action='User created',
                description=f'New user created: {instance.username} ({instance.role})',
            )
        except Exception:
            pass
