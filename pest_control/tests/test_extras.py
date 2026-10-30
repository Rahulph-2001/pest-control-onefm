"""Contracts/AMC, attendance sync, daily manpower report, certificate, dashboard."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from pest_control import allocation
from pest_control.contracts import generate_service_requests
from pest_control.pest_control.report.daily_manpower_deployment.daily_manpower_deployment import execute
from pest_control.tests import fixtures as fx

CONTRACT_START, CONTRACT_END = "2026-11-01", "2027-01-31"


class PestControlExtras(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.base = fx.base_records()
		cls.users = fx.users()
		cls.tech = fx.verified_worker("Arun", user_email=cls.users.field)
		cls.sup = fx.verified_worker("Sanjay", roles=("Supervisor",))
		# OneFM's Contracts insert commits, so create it here, not inside a test
		cls.contract = fx.contract(cls.base, CONTRACT_START, CONTRACT_END, [
			{"operations_site": cls.base.site, "pest_category": "Cockroaches", "visit_frequency": "Monthly"},
			{"operations_site": cls.base.site, "pest_category": "Termites", "visit_frequency": "Quarterly"},
		])
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("pc_extras")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="pc_extras")

	def free_day(self, start_back):
		"""A past day without attendance or roster entries for the crew (the demo
		journey commits real ones)."""
		for back in range(start_back, start_back + 90):
			day = getdate(add_days(nowdate(), -back))
			busy = {"employee": ("in", [self.tech, self.sup]), "docstatus": ("<", 2), "attendance_date": day}
			if not frappe.db.exists("Attendance", busy):
				return day
		self.fail("no free day")

	def completed_visit(self, day_offset, actual_day):
		request = fx.service_request(self.base).name
		visit = fx.visit(self.base, request, day_offset=day_offset, technicians=1, supervisors=1).name
		frappe.set_user(self.users.ops)
		allocation.schedule_visit(visit)
		allocation.allocate(visit, self.tech, "Technician")
		allocation.allocate(visit, self.sup, "Supervisor")
		allocation.start_visit(visit)
		frappe.set_user(self.users.field)
		report = frappe.get_doc(
			{
				"doctype": "Pest Completion Report",
				"visit": visit,
				"actual_start": f"{actual_day} 09:00:00",
				"actual_end": f"{actual_day} 11:00:00",
				"work_performed": "Gel bait applied in kitchens.",
				"materials_used": [{"item_code": self.base.item, "qty": 2, "uom": "Nos"}],
			}
		).insert()
		report.submit()
		frappe.set_user("Administrator")
		return visit, report.name

	# contracts / AMC ------------------------------------------------------

	def test_contract_generates_requests_idempotently(self):
		frappe.set_user(self.users.ops)
		first = generate_service_requests(self.contract)
		# monthly Nov, Dec, Jan + quarterly Nov
		self.assertEqual(len(first["created"]), 4)
		requests = frappe.get_all(
			"Pest Service Request", filters={"contract": self.contract},
			fields=["customer", "operations_site", "pest_category", "requested_date", "status"],
		)
		self.assertEqual(len(requests), 4)
		self.assertTrue(all(r.customer == self.base.customer and r.status == "Open" for r in requests))
		self.assertEqual(
			sorted(str(r.requested_date) for r in requests if r.pest_category == "Cockroaches"),
			["2026-11-01", "2026-12-01", "2027-01-01"],
		)

		again = generate_service_requests(self.contract)
		self.assertEqual((len(again["created"]), again["skipped"]), (0, 4))

	def test_contract_request_must_match_customer(self):
		with self.assertRaises(frappe.ValidationError):
			fx.service_request(
				self.base, customer=self.base.other_customer, crm_reference_doctype=None,
				crm_reference_name=None, contract=self.contract,
			)
		with self.assertRaises(frappe.ValidationError):
			fx.service_request(self.base, crm_reference_doctype=None, crm_reference_name=None)

	def test_field_user_cannot_generate_requests(self):
		frappe.set_user(self.users.field)
		with self.assertRaises(frappe.PermissionError):
			generate_service_requests(self.contract)

	# attendance sync ------------------------------------------------------

	def test_completion_marks_crew_present(self):
		day = self.free_day(3)
		visit, _report = self.completed_visit(30, day)
		for employee in (self.tech, self.sup):
			att = frappe.db.get_value(
				"Attendance", {"employee": employee, "attendance_date": day, "docstatus": 1},
				["status", "working_hours", "reference_doctype", "reference_docname"], as_dict=True,
			)
			self.assertIsNotNone(att, employee)
			self.assertEqual(att.status, "Present")
			self.assertEqual(att.working_hours, 2)
			self.assertEqual(att.reference_doctype, "Pest Visit Assignment")
			self.assertEqual(frappe.db.get_value("Pest Visit Assignment", att.reference_docname, "visit"), visit)
		self.assertTrue(frappe.db.exists("Pest Audit Event", {"event_type": "Attendance Synced", "reference_name": visit}))

	def test_existing_attendance_is_left_alone(self):
		day = self.free_day(40)
		existing = frappe.get_doc(
			{"doctype": "Attendance", "employee": self.tech, "attendance_date": day, "status": "Half Day",
				"company": self.base.company}
		)
		existing.insert(ignore_permissions=True)
		existing.submit()
		self.completed_visit(31, day)
		self.assertEqual(frappe.db.count("Attendance", {"employee": self.tech, "attendance_date": day, "docstatus": 1}), 1)
		self.assertEqual(frappe.db.get_value("Attendance", existing.name, "status"), "Half Day")

	# daily manpower report ------------------------------------------------

	def test_daily_manpower_report_shows_crew_and_gaps(self):
		request = fx.service_request(self.base).name
		visit = fx.visit(self.base, request, day_offset=32, technicians=1, supervisors=1).name
		frappe.set_user(self.users.ops)
		allocation.allocate(visit, self.tech, "Technician")
		_columns, rows = execute({"date": add_days(nowdate(), 32)})
		rows = [r for r in rows if r["visit"] == visit]
		self.assertEqual(len(rows), 2)
		assigned = [r for r in rows if r.get("employee")]
		self.assertEqual(assigned[0]["employee"], self.tech)
		self.assertTrue(assigned[0]["employee_schedule"])
		gap = [r for r in rows if not r.get("employee")]
		self.assertEqual((gap[0]["staffing_role"], gap[0]["employee_name"]), ("Supervisor", "Unfilled"))
		self.assertEqual(frappe.db.get_value("Pest Service Visit", visit, "fully_staffed"), 0)
		allocation.allocate(visit, self.sup, "Supervisor")
		self.assertEqual(frappe.db.get_value("Pest Service Visit", visit, "fully_staffed"), 1)

	# certificate and dashboard ---------------------------------------------

	def test_service_certificate_renders(self):
		_visit, report = self.completed_visit(33, self.free_day(80))
		html = frappe.get_print("Pest Completion Report", report, "Pest Service Certificate")
		self.assertIn("PEST CONTROL SERVICE CERTIFICATE", html)
		self.assertIn(self.base.customer, html)
		self.assertIn(report, html)
		self.assertIn(frappe.db.get_value("Employee", self.tech, "employee_name"), html)
		self.assertEqual(
			frappe.get_meta("Pest Completion Report").default_print_format, "Pest Service Certificate"
		)

	def test_workspace_and_cards_exist(self):
		self.assertTrue(frappe.db.exists("Workspace", "Pest Control"))
		for card in ("Pest Visits Today", "Pest Understaffed Visits", "Pest Pending Verifications", "Pest Active Contracts"):
			self.assertTrue(frappe.db.exists("Number Card", card), card)
		self.assertTrue(frappe.db.exists("Dashboard Chart", "Pest Visits by Status"))
		self.assertTrue(frappe.db.exists("Report", "Daily Manpower Deployment"))
