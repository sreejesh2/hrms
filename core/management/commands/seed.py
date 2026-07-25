from django.core.management.base import BaseCommand, CommandError

from core.seed import DEFAULT_GROUPS, SEED_GROUPS, run_seed


class Command(BaseCommand):
    help = (
        "Seed foundation data: permissions, roles, org settings, and default catalogs. "
        "Idempotent — safe to re-run after pulling new permission codes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            nargs="+",
            choices=sorted(SEED_GROUPS.keys()),
            metavar="GROUP",
            help=(
                "Seed only these groups. Choices: "
                + ", ".join(sorted(SEED_GROUPS.keys()))
            ),
        )
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_groups",
            help="List available seed groups and exit.",
        )
        parser.add_argument(
            "--admin",
            action="store_true",
            help="Also ensure demo admin user (default: admin@example.com / admin123).",
        )
        parser.add_argument(
            "--demo",
            action="store_true",
            help=(
                "Replace all employees with 5 demo staff, create GEN shift, "
                "and generate this month's attendance (destructive)."
            ),
        )
        parser.add_argument(
            "--admin-email",
            default="admin@example.com",
            help="Email for --admin (default: admin@example.com).",
        )
        parser.add_argument(
            "--admin-password",
            default="admin123",
            help="Password for new admin or when --reset-admin-password is set.",
        )
        parser.add_argument(
            "--reset-admin-password",
            action="store_true",
            help="Reset the admin password even if the user already exists.",
        )

    def handle(self, *args, **options):
        if options["list_groups"]:
            self.stdout.write("Seed groups:")
            for key, desc in SEED_GROUPS.items():
                if key in DEFAULT_GROUPS:
                    mark = " (default)"
                elif key == "admin":
                    mark = " (opt-in via --admin or --only admin)"
                else:
                    mark = " (opt-in via --demo or --only demo; replaces employees)"
                self.stdout.write(f"  {key:12}  {desc}{mark}")
            return

        groups = options["only"]
        try:
            stats = run_seed(
                groups,
                with_admin=options["admin"] or (groups and "admin" in groups),
                with_demo=options["demo"] or (groups and "demo" in groups),
                admin_email=options["admin_email"],
                admin_password=options["admin_password"],
                reset_admin_password=options["reset_admin_password"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write(f"  groups: {', '.join(stats.get('groups', []))}")

        lines = [
            ("permissions", "permissions"),
            ("roles", "roles"),
            ("organization", "organization"),
            ("leave_types", "leave types"),
            ("expense_categories", "expense categories"),
            ("salary_components", "salary components"),
            ("statutory_rules", "statutory rules"),
            ("ot_policies", "OT policies"),
            ("competencies", "competencies"),
        ]
        for key, label in lines:
            if key in stats:
                created_key = (
                    f"{key}_created"
                    if key != "organization"
                    else "organization_created"
                )
                created = stats.get(created_key, 0)
                extra = f" (+{created} new)" if created else ""
                self.stdout.write(f"  {label}: {stats[key]}{extra}")

        if "admin_email" in stats:
            bits = [stats["admin_email"]]
            if stats.get("admin_created"):
                bits.append("created")
            if stats.get("admin_role_attached"):
                bits.append("Admin role attached")
            if stats.get("admin_password_reset"):
                bits.append("password reset")
            self.stdout.write(f"  admin: {', '.join(bits)}")
            if stats.get("admin_created") or stats.get("admin_password_reset"):
                self.stdout.write(
                    self.style.WARNING(
                        f"  login: {options['admin_email']} / {options['admin_password']}"
                    )
                )

        if "employees" in stats:
            self.stdout.write(
                self.style.WARNING(
                    f"  demo employees: {stats['employees']} "
                    f"({', '.join(stats.get('employee_codes', []))})"
                )
            )
            self.stdout.write(
                f"  shift: {stats.get('shift')} · calendar: {stats.get('calendar')}"
            )
            self.stdout.write(
                f"  attendance: {stats.get('attendance_from')} → "
                f"{stats.get('attendance_through')} "
                f"({stats.get('punches')} punches, "
                f"{stats.get('attendance_rows')} daily rows)"
            )
