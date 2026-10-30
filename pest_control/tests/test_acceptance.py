"""Acceptance cases from the implementation plan (page 6), numbered to match.

Run: bench --site pest.localhost run-tests --app pest_control
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_datetime, getdate, nowdate

from pest_control import allocation
from pest_control.allocation import onefm_schedule_write
from pest_control.tests import fixtures as fx
from pest_control.utils import service_write
from pest_control.verification import decide


def schedule_of(assignment):
	return frappe.db.get_value("Pest Visit Assignment", assignment, "employee_schedule")


class PestControlAcceptance(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.base = fx.base_records()
		cls.users = fx.users()
		cls.tech_a = fx.verified_worker("Arun", user_email=cls.users.field)
		cls.tech_b = fx.verified_worker("Bilal", user_email=cls.users.field2)
		cls.tech_c = fx.verified_worker("Chitra")
		cls.sup = fx.verified_worker("Sanjay", roles=("Supervisor",), qualified=True)
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("pc_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="pc_test")

	# helpers -------------------------------------------------------------

	def new_visit(self, day_offset, **kw):
		request = fx.service_request(self.base).name
		kw.setdefault("technicians", 1)
		kw.setdefault("supervisors", 0)
		return fx.visit(self.base, request, day_offset=day_offset, **kw)

	def as_ops(self):
		frappe.set_user(self.users.ops)

	def staffed_visit(self, day_offset):
		visit = self.new_visit(day_offset, technicians=1, supervisors=1)
		self.as_ops()
		allocation.schedule_visit(visit.name)
		allocation.allocate(visit.name, self.tech_a, "Technician")
		allocation.allocate(visit.name, self.sup, "Supervisor")
		return visit.name

	# 1 -------------------------------------------------------------------

	def test_01_enquiry_links_to_request_for_customer_site(self):
		request = fx.service_request(self.base)
		self.assertEqual(request.status, "Open")
		self.assertEqual(request.crm_reference_name, self.base.lead)

		with self.assertRaises(frappe.ValidationError):
			fx.service_request(self.base, customer=self.base.other_customer)
		with self.assertRaises(frappe.ValidationError):
			fx.service_request(self.base, crm_reference_doctype="Customer", crm_reference_name=self.base.customer)
		with self.assertRaises(frappe.ValidationError):
			fx.service_request(self.base, crm_reference_name="does-not-exist")

	# 2 -------------------------------------------------------------------

	def test_02_visit_validates_times_counts_and_onefm_site(self):
		visit = self.new_visit(2)
		self.assertEqual(visit.operations_site, self.base.site)
		self.assertEqual(visit.status, "Draft")
		self.assertTrue("one_fm" in frappe.get_installed_apps())

		with self.assertRaises(frappe.ValidationError):
			self.new_visit(2, start="12:00:00", end="09:00:00")
		with self.assertRaises(frappe.ValidationError):
			self.new_visit(2, technicians=-1)
		with self.assertRaises(frappe.ValidationError):
			self.new_visit(2, technicians=0, supervisors=0)

	# 3 -------------------------------------------------------------------

	def test_03_allocation_creates_matching_onefm_schedule(self):
		visit = self.new_visit(3)
		self.as_ops()
		assignment = allocation.allocate(visit.name, self.tech_a, "Technician")

		schedule = frappe.get_doc("Employee Schedule", schedule_of(assignment))
		self.assertEqual(schedule.employee, self.tech_a)
		self.assertEqual(schedule.reference_doctype, "Pest Visit Assignment")
		self.assertEqual(schedule.reference_docname, assignment)
		self.assertEqual(schedule.employee_availability, "Working")
		self.assertEqual(schedule.site, self.base.site)
		self.assertEqual(get_datetime(schedule.start_datetime), get_datetime(visit.scheduled_start))
		self.assertEqual(get_datetime(schedule.end_datetime), get_datetime(visit.scheduled_end))

		# the native roster holds exactly one schedule for this assignment
		self.assertEqual(
			frappe.db.count("Employee Schedule", {"reference_docname": assignment}), 1
		)
		self.assertIn("Technicians 1/1", frappe.db.get_value("Pest Service Visit", visit.name, "coverage_summary"))

	# 4 -------------------------------------------------------------------

	def test_04_ineligible_workers_are_rejected(self):
		visit = self.new_visit(4)

		def rejects(employee, role="Technician"):
			frappe.set_user(self.users.ops)
			with self.assertRaises(frappe.ValidationError):
				allocation.allocate(visit.name, employee, role)
			frappe.set_user("Administrator")

		# no verification record at all
		rejects(fx.employee("Nobody"))

		# pending / rejected / revoked verification
		for status in ("Pending", "Rejected", "Revoked"):
			emp = fx.verified_worker(f"Status{status}")
			doc = frappe.get_doc("Pest Employee Verification", {"employee": emp})
			fx._force_status(doc, status)
			rejects(emp)

		# not authorized for the role
		rejects(self.tech_c, "Supervisor")

		# inactive employment
		inactive = fx.verified_worker("Inactive")
		frappe.db.set_value("Employee", inactive, "status", "Inactive")
		rejects(inactive)

		# missing and expired qualification
		rejects(fx.verified_worker("Unqualified", qualified=False))
		expired = fx.verified_worker("Expiring", qual_valid_days=2)  # expires before visit day 4
		rejects(expired)

		# no working period
		no_shift = fx.verified_worker("NoShift")
		frappe.db.set_value("Shift Assignment", {"employee": no_shift}, "status", "Inactive")
		rejects(no_shift)

		# approved leave
		on_leave = fx.verified_worker("OnLeave")
		frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": on_leave,
				"leave_type": frappe.db.get_value("Leave Type", {}, "name") or "Casual Leave",
				"from_date": add_days(nowdate(), 4),
				"to_date": add_days(nowdate(), 4),
				"status": "Approved",
				"docstatus": 1,
				"company": self.base.company,
				"posting_date": nowdate(),
			}
		).db_insert()
		rejects(on_leave)

		# visit outside working hours (shift is 07:00-19:00)
		late = self.new_visit(4, start="18:00:00", end="21:00:00")
		frappe.set_user(self.users.ops)
		with self.assertRaises(frappe.ValidationError):
			allocation.allocate(late.name, self.tech_a, "Technician")

	# 5 -------------------------------------------------------------------

	def test_05_overlaps_rejected_across_custom_and_native_paths(self):
		first = self.new_visit(5, start="09:00:00", end="12:00:00")
		second = self.new_visit(5, start="11:00:00", end="13:00:00")
		self.as_ops()
		allocation.allocate(first.name, self.tech_a, "Technician")

		# competing request for the same employee and time
		with self.assertRaises(frappe.ValidationError):
			allocation.allocate(second.name, self.tech_a, "Technician")

		# native OneFM schedule overlapping pest work is refused by the hook
		frappe.set_user("Administrator")
		native = frappe.get_doc(
			{
				"doctype": "Employee Schedule",
				"employee": self.tech_a,
				"date": add_days(nowdate(), 5),
				"shift": self.base.shift,
				"employee_availability": "Working",
				"roster_type": "Over-Time",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			native.insert(ignore_permissions=True)

		# existing non-pest OneFM work blocks pest allocation
		day6 = add_days(nowdate(), 6)
		frappe.get_doc(
			{
				"doctype": "Employee Schedule",
				"employee": self.tech_b,
				"date": day6,
				"shift": self.base.shift,
				"employee_availability": "Working",
				"roster_type": "Basic",
			}
		).insert(ignore_permissions=True)
		third = self.new_visit(6)
		self.as_ops()
		with self.assertRaises(frappe.ValidationError):
			allocation.allocate(third.name, self.tech_b, "Technician")

		# a day off on the OneFM roster blocks allocation
		day7 = add_days(nowdate(), 7)
		frappe.set_user("Administrator")
		frappe.get_doc(
			{"doctype": "Employee Schedule", "employee": self.tech_c, "date": day7,
				"employee_availability": "Day Off", "roster_type": "Basic"}
		).insert(ignore_permissions=True)
		fourth = self.new_visit(7)
		self.as_ops()
		with self.assertRaises(frappe.ValidationError):
			allocation.allocate(fourth.name, self.tech_c, "Technician")

	# 6 -------------------------------------------------------------------

	def test_06_reschedule_moves_onefm_schedule_idempotently(self):
		visit = self.new_visit(8)
		self.as_ops()
		assignment = allocation.allocate(visit.name, self.tech_a, "Technician")
		day9 = getdate(add_days(nowdate(), 9))

		result = allocation.reschedule_visit(visit.name, f"{day9} 10:00:00", f"{day9} 13:00:00", "Customer request")
		self.assertTrue(result["changed"])
		new_schedule = frappe.get_doc("Employee Schedule", schedule_of(assignment))
		self.assertEqual(getdate(new_schedule.date), day9)
		self.assertEqual(get_datetime(new_schedule.start_datetime), get_datetime(f"{day9} 10:00:00"))

		# retrying the same request does not duplicate anything
		again = allocation.reschedule_visit(visit.name, f"{day9} 10:00:00", f"{day9} 13:00:00", "Customer request")
		self.assertFalse(again["changed"])
		self.assertEqual(frappe.db.count("Employee Schedule", {"employee": self.tech_a, "reference_doctype": "Pest Visit Assignment"}), 1)

		# a failing reschedule keeps the original valid schedule
		blocker = self.new_visit(10)
		allocation.allocate(blocker.name, self.tech_a, "Technician")
		day10 = getdate(add_days(nowdate(), 10))
		with self.assertRaises(frappe.ValidationError):
			allocation.reschedule_visit(visit.name, f"{day10} 09:00:00", f"{day10} 12:00:00", "Clash")
		self.assertEqual(schedule_of(assignment), new_schedule.name)
		self.assertTrue(frappe.db.exists("Employee Schedule", new_schedule.name))
		self.assertEqual(getdate(frappe.db.get_value("Pest Service Visit", visit.name, "scheduled_start")), day9)

	# 7 -------------------------------------------------------------------

	def test_07_replace_worker_keeps_history_and_counts(self):
		visit = self.new_visit(11, technicians=1, supervisors=1)
		self.as_ops()
		old = allocation.allocate(visit.name, self.tech_a, "Technician")
		old_schedule = schedule_of(old)

		# one person cannot fill two roles on the same visit
		with self.assertRaises(frappe.ValidationError):
			allocation.allocate(visit.name, self.tech_a, "Supervisor")

		new = allocation.replace_assignment(old, self.tech_b, "Arun called in sick")
		old_doc = frappe.get_doc("Pest Visit Assignment", old)
		self.assertEqual(old_doc.status, "Replaced")
		self.assertEqual(old_doc.end_reason, "Arun called in sick")
		self.assertEqual(old_doc.replaced_by, new)
		self.assertEqual(old_doc.released_employee_schedule, old_schedule)
		self.assertFalse(frappe.db.exists("Employee Schedule", old_schedule))
		self.assertEqual(frappe.db.get_value("Pest Visit Assignment", new, "replaces"), old)
		self.assertEqual(frappe.db.count("Pest Visit Assignment", {"visit": visit.name, "status": "Active"}), 1)

		# replacing with an ineligible worker changes nothing
		with self.assertRaises(frappe.ValidationError):
			allocation.replace_assignment(new, fx.employee("Nobody"), "test")
		self.assertEqual(frappe.db.get_value("Pest Visit Assignment", new, "status"), "Active")
		self.assertTrue(frappe.db.exists("Employee Schedule", schedule_of(new)))

	# 8 -------------------------------------------------------------------

	def test_08_start_gate_and_completion_report(self):
		visit = self.new_visit(12, technicians=1, supervisors=1)
		self.as_ops()
		allocation.schedule_visit(visit.name)
		allocation.allocate(visit.name, self.tech_a, "Technician")
		with self.assertRaises(frappe.ValidationError):
			allocation.start_visit(visit.name)  # understaffed

		allocation.allocate(visit.name, self.sup, "Supervisor")
		allocation.start_visit(visit.name)
		self.assertEqual(frappe.db.get_value("Pest Service Visit", visit.name, "status"), "In Progress")

		frappe.set_user(self.users.field)  # tech_a's account
		report = frappe.get_doc(
			{
				"doctype": "Pest Completion Report",
				"visit": visit.name,
				"actual_start": add_days(frappe.utils.now_datetime(), -1),
				"actual_end": frappe.utils.now_datetime(),
				"work_performed": "Gel bait applied in kitchens and drains.",
				"materials_used": [{"item_code": self.base.item, "qty": 3, "uom": "Nos"}],
			}
		)
		report.insert()
		report.submit()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Pest Service Visit", visit.name, "status"), "Completed")
		self.assertEqual(
			frappe.db.get_value("Pest Service Request", visit.service_request, "status"), "Completed"
		)

	# 9 -------------------------------------------------------------------

	def test_09_invalid_input_and_guarded_fields(self):
		visit = self.new_visit(13)

		# invalid material quantity and unit
		visit.append("planned_materials", {"item_code": self.base.item, "qty": 0, "uom": "Nos"})
		with self.assertRaises(frappe.ValidationError):
			visit.save()
		visit.reload()
		visit.append("planned_materials", {"item_code": self.base.item, "qty": 1, "uom": "Litre"})
		with self.assertRaises(frappe.ValidationError):
			visit.save()
		visit.reload()

		# field user cannot allocate
		frappe.set_user(self.users.field)
		with self.assertRaises(frappe.PermissionError):
			allocation.allocate(visit.name, self.tech_a, "Technician")

		# direct API attempts on guarded fields
		frappe.set_user(self.users.ops)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Pest Service Visit", visit.name, "status", "Completed")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{"doctype": "Pest Visit Assignment", "visit": visit.name, "staffing_role": "Technician",
					"employee": self.tech_a, "status": "Active"}
			).insert(ignore_permissions=True)

		frappe.set_user(self.users.hr)
		verification = frappe.get_doc("Pest Employee Verification", {"employee": self.tech_c})
		verification.verification_status = "Revoked"
		with self.assertRaises(frappe.PermissionError):
			verification.save()

		# self-approval: the HR verifier's own employee record
		frappe.set_user("Administrator")
		own = fx.verified_worker("HrSelf", user_email=self.users.hr)
		own_doc = frappe.get_doc("Pest Employee Verification", {"employee": own})
		fx._force_status(own_doc, "Pending")
		frappe.set_user(self.users.hr)
		with self.assertRaises(frappe.PermissionError):
			decide("Pest Employee Verification", own_doc.name, "Verified")

		# native edit of a pest-linked OneFM schedule is refused
		frappe.set_user(self.users.ops)
		assignment = allocation.allocate(visit.name, self.tech_a, "Technician")
		frappe.set_user("Administrator")
		schedule = frappe.get_doc("Employee Schedule", schedule_of(assignment))
		schedule.employee = self.tech_c
		with self.assertRaises(frappe.PermissionError):
			schedule.save(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("Employee Schedule", schedule.name, ignore_permissions=True, force=True)

	# 10 ------------------------------------------------------------------

	def test_10_revocation_after_assignment_blocks_start_and_is_audited(self):
		visit_name = self.staffed_visit(14)

		frappe.set_user(self.users.hr)
		decide("Pest Employee Verification", self.tech_a, "Revoked", "Licence under investigation")
		self.as_ops()
		with self.assertRaises(frappe.ValidationError):
			allocation.start_visit(visit_name)

		frappe.set_user(self.users.hr)
		decide("Pest Employee Verification", self.tech_a, "Verified", "Investigation closed")
		self.as_ops()
		allocation.start_visit(visit_name)

		events = frappe.get_all(
			"Pest Audit Event",
			filters={"reference_name": self.tech_a, "reference_doctype": "Pest Employee Verification"},
			fields=["event_type", "actor", "reason", "event_time"],
			order_by="creation asc",
		)
		self.assertEqual([e.event_type for e in events[-2:]], ["Verification Revoked", "Verification Verified"])
		self.assertTrue(all(e.actor == self.users.hr and e.event_time for e in events[-2:]))
		self.assertEqual(events[-2].reason, "Licence under investigation")

		# changing evidence after approval invalidates it
		frappe.set_user(self.users.hr)
		doc = frappe.get_doc("Pest Employee Verification", self.tech_a)
		doc.identity_document_number = "ID-CHANGED"
		doc.save()
		self.assertEqual(doc.verification_status, "Pending")

	# 11 ------------------------------------------------------------------

	def test_11_record_and_file_access(self):
		visit_a = self.new_visit(15)
		visit_b = self.new_visit(15, start="13:00:00", end="15:00:00")
		self.as_ops()
		allocation.allocate(visit_a.name, self.tech_a, "Technician")
		allocation.allocate(visit_b.name, self.tech_b, "Technician")

		frappe.set_user(self.users.field)
		visible = frappe.get_list("Pest Service Visit", pluck="name")
		self.assertIn(visit_a.name, visible)
		self.assertNotIn(visit_b.name, visible)
		self.assertFalse(frappe.has_permission("Pest Service Visit", "read", visit_b.name))
		self.assertFalse(frappe.has_permission("Pest Service Visit", "write", visit_a.name))

		# HR evidence and verification records are closed to field users and ops managers
		evidence_url = frappe.db.get_value("Pest Employee Verification", self.tech_b, "identity_evidence")
		file_name = frappe.db.get_value("File", {"file_url": evidence_url})
		for user in (self.users.field, self.users.ops):
			frappe.set_user(user)
			self.assertFalse(frappe.has_permission("Pest Employee Verification", "read", self.tech_b))
			self.assertFalse(frappe.get_doc("File", file_name).is_downloadable())
			with self.assertRaises(frappe.PermissionError):
				decide("Pest Employee Verification", self.tech_b, "Revoked", "x")

		# nobody edits or deletes audit history
		frappe.set_user("Administrator")
		event = frappe.get_all("Pest Audit Event", limit=1, pluck="name")[0]
		for user in (self.users.field, self.users.ops, "Administrator"):
			frappe.set_user(user)
			with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
				frappe.delete_doc("Pest Audit Event", event)
