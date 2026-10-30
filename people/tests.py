from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .importer import apply_plan, biometric_from_code, build_plan
from .models import Department, Division, Employee, Position

HEADER = (
    "CODE,EMPNAME,DIV_DESC,DEP_DESCR,POS_DESCR,SPONSOR_DESC,JOIN_DATE,"
    "ACTIVE_STAT,WORK_STAT,SHIFT_STAT\n"
)
SAMPLE = HEADER + (
    "A1P104,RYAN PISIT LONTO,INJECTION MOULDING,Maintenance,Maintenance In charge,,"
    "14/06/2007 0:00,Active,Working,DAYSHIFT\n"
    "A1P115,RUHUL AMIN BABU,DESPATCH,DESPATCH,Helper,,06/10/2011 0:00,Active,Working,DAYSHIFT\n"
    'A1P160,"VARUGHESE THOMAS MEMANA\n",Administration,Administration,General Manager,,'
    "18/05/2017 0:00,Active,Working,REGULAR\n"
)


class EmployeeImportTests(TestCase):
    def test_machine_id_is_number_at_end_of_code(self):
        self.assertEqual(biometric_from_code("A1P104"), "104")
        self.assertEqual(biometric_from_code("A1P007"), "7")
        self.assertEqual(biometric_from_code("ABC"), "")

    def test_creates_employees_and_masters(self):
        plan = build_plan(SAMPLE)
        self.assertEqual(plan.counts["create"], 3)
        self.assertEqual(
            plan.new_masters["Divisions"],
            ["Administration", "DESPATCH", "INJECTION MOULDING"],
        )

        result = apply_plan(plan)

        self.assertEqual(result["created"], 3)
        ryan = Employee.objects.get(employee_code="A1P104")
        self.assertEqual((ryan.first_name, ryan.last_name), ("RYAN", "PISIT LONTO"))
        self.assertEqual(ryan.biometric_id, "104")
        self.assertEqual(ryan.date_of_joining, date(2007, 6, 14))
        self.assertEqual(ryan.status, Employee.Status.ACTIVE)
        self.assertEqual(ryan.department.description, "Maintenance")
        self.assertEqual(ryan.department.division.description, "INJECTION MOULDING")
        # Line break inside the quoted name cell is cleaned away
        self.assertEqual(Employee.objects.get(employee_code="A1P160").last_name, "THOMAS MEMANA")
        self.assertEqual(Division.objects.count(), 3)
        self.assertEqual(Position.objects.filter(description="Helper").count(), 1)

    def test_reimport_creates_no_duplicates(self):
        apply_plan(build_plan(SAMPLE))

        plan = build_plan(SAMPLE)

        self.assertEqual(plan.counts["unchanged"], 3)
        self.assertFalse(plan.can_apply)
        self.assertEqual(Employee.objects.count(), 3)
        self.assertEqual(Department.objects.filter(description="DESPATCH").count(), 1)

    def test_changed_row_updates_existing_employee(self):
        apply_plan(build_plan(SAMPLE))
        changed = SAMPLE.replace("RUHUL AMIN BABU,DESPATCH,DESPATCH,Helper", "RUHUL AMIN BABU,DESPATCH,DESPATCH,Driver")

        plan = build_plan(changed)
        self.assertEqual(plan.counts["update"], 1)
        apply_plan(plan)

        self.assertEqual(Employee.objects.count(), 3)
        self.assertEqual(Employee.objects.get(employee_code="A1P115").position.description, "Driver")

    def test_matches_masters_ignoring_case_and_spaces(self):
        Department.objects.create(code="MAINT", description="MAINTENANCE")

        apply_plan(build_plan(SAMPLE))

        self.assertEqual(Employee.objects.get(employee_code="A1P104").department.code, "MAINT")
        self.assertEqual(Department.objects.filter(description__iexact="maintenance").count(), 1)

    def test_same_code_twice_is_skipped(self):
        text = SAMPLE + "A1P104,SOMEONE ELSE,DESPATCH,DESPATCH,Helper,,01/01/2020,Active,Working,\n"

        plan = build_plan(text)

        self.assertEqual([r.code for r in plan.error_rows], ["A1P104", "A1P104"])
        apply_plan(plan)
        self.assertFalse(Employee.objects.filter(employee_code="A1P104").exists())

    def test_two_codes_with_same_number_are_skipped(self):
        text = SAMPLE + "B2P104,OTHER PERSON,DESPATCH,DESPATCH,Helper,,01/01/2020,Active,Working,\n"

        plan = build_plan(text)

        self.assertEqual(sorted(r.code for r in plan.error_rows), ["A1P104", "B2P104"])

    def test_machine_id_taken_by_other_employee_is_error(self):
        Employee.objects.create(employee_code="OLD1", first_name="Old", biometric_id="104")

        plan = build_plan(SAMPLE)

        row = next(r for r in plan.rows if r.code == "A1P104")
        self.assertEqual(row.action, "error")
        self.assertIn("OLD1", row.errors[0])

    def test_bad_date_and_missing_column(self):
        bad = SAMPLE.replace("14/06/2007 0:00", "2007-31-31")
        self.assertEqual(build_plan(bad).error_rows[0].code, "A1P104")

        self.assertTrue(build_plan("NAME\nRyan\n").file_errors)

    def test_inactive_and_vacation_status(self):
        text = HEADER + (
            "A1P1,LEFT PERSON,X,Y,Z,,01/01/2020,Inactive,Working,\n"
            "A1P2,AWAY PERSON,X,Y,Z,,01/01/2020,Active,Vacation,\n"
        )
        apply_plan(build_plan(text))

        self.assertEqual(Employee.objects.get(employee_code="A1P1").status, Employee.Status.INACTIVE)
        self.assertEqual(Employee.objects.get(employee_code="A1P2").status, Employee.Status.ON_LEAVE)

    def test_warns_on_unusual_division(self):
        text = HEADER + (
            "A1P1,A ONE,THERMOFORMING,PRODUCTION (TF),Op,,01/01/2020,Active,Working,\n"
            "A1P2,A TWO,THERMOFORMING,PRODUCTION (TF),Op,,01/01/2020,Active,Working,\n"
            "A1P3,A THREE,INJECTION MOULDING,PRODUCTION (TF),Op,,01/01/2020,Active,Working,\n"
        )
        plan = build_plan(text)
        warned = {r.code: r.warnings for r in plan.warning_rows}

        self.assertIn("usually under division THERMOFORMING", warned["A1P3"][0])
        self.assertEqual(set(warned), {"A1P3"})

    def test_creates_missing_shifts_once(self):
        from attendance.models import ShiftAssignment, WorkShift

        WorkShift.objects.create(code="DAYSHIFT", name="Day")
        text = SAMPLE + (
            "A1P437,ALYAA SAEED,Administration,Administration,Office Assistant,,"
            "05/06/2023 0:00,Active,Working,EMRAT SHFT\n"
        )
        plan = build_plan(text)
        self.assertEqual(
            plan.new_masters["Shifts (set their times after import)"],
            ["EMRAT SHFT", "REGULAR"],
        )

        result = apply_plan(plan)

        self.assertEqual(result["shifts_created"], 2)
        self.assertEqual(result["shifts"], 4)
        self.assertEqual(WorkShift.objects.filter(code="REGULAR").count(), 1)
        a = ShiftAssignment.objects.get(employee__employee_code="A1P437", is_active=True)
        self.assertEqual(a.shift.code, "EMRAT SHFT")
        # Second import finds the shifts it created: nothing new
        self.assertNotIn(
            "Shifts (set their times after import)", build_plan(text).new_masters
        )

    def test_assigns_existing_shift(self):
        from attendance.models import ShiftAssignment, WorkShift

        WorkShift.objects.create(code="DAYSHIFT", name="Day")

        result = apply_plan(build_plan(SAMPLE))

        self.assertEqual(result["shifts"], 3)  # REGULAR is created too
        a = ShiftAssignment.objects.get(employee__employee_code="A1P104", is_active=True)
        self.assertEqual(a.shift.code, "DAYSHIFT")
        self.assertEqual(a.effective_from, date(2007, 6, 14))


class EmployeeImportViewTests(TestCase):
    def setUp(self):
        from accounts.models import Role
        from accounts.rbac import seed_rbac

        seed_rbac()
        user = get_user_model().objects.create_user(email="admin@example.com", password="x")
        user.roles.set([Role.objects.get(name="Admin")])
        self.client.force_login(user)

    def test_preview_saves_nothing_then_confirm_imports(self):
        upload = SimpleUploadedFile("HRMS.csv", SAMPLE.encode(), content_type="text/csv")

        resp = self.client.post("/people/import/", {"file": upload})

        self.assertContains(resp, "3 new")
        self.assertContains(resp, "Confirm import")
        self.assertEqual(Employee.objects.count(), 0)

        resp = self.client.post("/people/import/", {"action": "apply"})

        self.assertRedirects(resp, "/people/")
        self.assertEqual(Employee.objects.count(), 3)

    def test_confirm_without_upload_redirects(self):
        resp = self.client.post("/people/import/", {"action": "apply"})

        self.assertRedirects(resp, "/people/import/")
        self.assertEqual(Employee.objects.count(), 0)

    def test_employee_role_cannot_open(self):
        from accounts.models import Role

        user = get_user_model().objects.create_user(email="e@example.com", password="x")
        user.roles.set([Role.objects.get(name="Employee")])
        self.client.force_login(user)

        resp = self.client.get("/people/import/")

        self.assertIn(resp.status_code, (302, 403))
