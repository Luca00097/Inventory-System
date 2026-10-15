from django.core.management.base import BaseCommand

from inventory.roles import ensure_roles


class Command(BaseCommand):
    help = "Create the Owner / Sales / Storekeeper role groups (use --reset to restore their default permissions)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Overwrite existing roles with the defaults.")

    def handle(self, *args, **options):
        touched = ensure_roles(reset=options["reset"])
        if touched:
            self.stdout.write(self.style.SUCCESS("Roles set up: " + ", ".join(touched)))
        else:
            self.stdout.write("All roles already exist. Use --reset to restore their default permissions.")
