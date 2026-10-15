from django.apps import AppConfig
from django.db.models.signals import m2m_changed, post_migrate


def _create_roles(sender, **kwargs):
    """Runs after `migrate`. Makes sure permissions exist, then creates the role groups."""
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions
    from django.contrib.contenttypes.management import create_contenttypes

    apps = kwargs.get("apps", global_apps)
    using = kwargs.get("using", "default")
    # Our app is listed before auth/contenttypes, so their own post_migrate hooks may
    # not have run yet. Create what we need ourselves; both calls are safe to repeat.
    # (They want the real app configs, with the migration-state `apps` passed alongside.)
    for config in (sender, global_apps.get_app_config("auth")):
        create_contenttypes(config, verbosity=0, using=using, apps=apps)
        create_permissions(config, verbosity=0, using=using, apps=apps)

    from .roles import ensure_roles
    ensure_roles()


def _staff_flag_for_role(sender, instance, action, reverse, pk_set, **kwargs):
    """Adding someone to a role group makes them staff, so they can use the pages their role allows."""
    if action != "post_add":
        return
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    from .roles import ROLE_NAMES

    User = get_user_model()
    if reverse:  # group.user_set.add(...)
        if instance.name in ROLE_NAMES:
            User.objects.filter(pk__in=pk_set, is_staff=False).update(is_staff=True)
    else:  # user.groups.add(...)
        if Group.objects.filter(pk__in=pk_set, name__in=ROLE_NAMES).exists() and not instance.is_staff:
            instance.is_staff = True
            instance.save(update_fields=["is_staff"])


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'

    def ready(self):
        post_migrate.connect(_create_roles, sender=self)
        from django.contrib.auth import get_user_model
        m2m_changed.connect(_staff_flag_for_role, sender=get_user_model().groups.through)
