"""Fictional demo data and a full enquiry-to-report journey.

bench --site pest.localhost execute pest_control.demo.setup_demo
bench --site pest.localhost execute pest_control.demo.run_journey
"""

import frappe
from frappe.utils import add_days, nowdate

from pest_control import allocation
from pest_control.tests import fixtures as fx


def setup_demo():
	"""Users, OneFM site/shift/roles, and verified and unverified workers."""
	frappe.set_user("Administrator")
	base = fx.base_records()
	users = fx.users()
	workers = {
		"Arun (verified technician)": fx.verified_worker("Arun", user_email=users.field),
		"Bilal (verified technician)": fx.verified_worker("Bilal", user_email=users.field2),
		"Sanjay (verified supervisor)": fx.verified_worker("Sanjay", roles=("Supervisor",)),
		"Uma (unverified)": fx.employee("Uma"),
	}
	for user in users.values():
		_set_password(user, "Demo@12345")
	data_contract = fx.contract(base, "2026-10-01", "2027-09-30", [
		{"operations_site": base.site, "pest_category": "Cockroaches", "visit_frequency": "Monthly"},
		{"operations_site": base.site, "pest_category": "Termites", "visit_frequency": "Quarterly"},
	])
	frappe.db.commit()
	return {"base": base, "users": users, "workers": workers, "contract": data_contract}


def _set_password(user, password):
	from frappe.utils.password import update_password

	update_password(user, password)


def _free_past_day(employees, max_days=25):
	for back in range(1, max_days):
		day = add_days(nowdate(), -back)
		if not frappe.db.exists("Employee Schedule", {"employee": ("in", employees), "date": day}):
			return day
	frappe.throw("No free day in the last few weeks for the demo crew.")


def run_journey(day_offset: int = 1):
	"""Enquiry -> request -> visit -> OneFM allocation -> start -> report."""
	data = setup_demo()
	base, users, workers = frappe._dict(data["base"]), frappe._dict(data["users"]), data["workers"]

	request = fx.service_request(base)
	visit = fx.visit(base, request.name, day_offset=day_offset, technicians=1, supervisors=1)

	frappe.set_user(users.ops)
	allocation.schedule_visit(visit.name)
	tech = allocation.allocate(visit.name, workers["Arun (verified technician)"], "Technician")
	sup = allocation.allocate(visit.name, workers["Sanjay (verified supervisor)"], "Supervisor")
	try:
		allocation.allocate(visit.name, workers["Uma (unverified)"], "Technician")
	except frappe.ValidationError:
		frappe.clear_messages()  # expected: unverified worker refused

	# bring the visit into the past so it can be started and reported in one run;
	# OneFM allows one Basic schedule per employee per day, so use a free day
	crew = [workers["Arun (verified technician)"], workers["Sanjay (verified supervisor)"]]
	day = _free_past_day(crew)
	allocation.reschedule_visit(visit.name, f"{day} 09:00:00", f"{day} 11:00:00", "Demo: bring forward")
	allocation.start_visit(visit.name)

	frappe.set_user(users.field)
	report = frappe.get_doc(
		{
			"doctype": "Pest Completion Report",
			"visit": visit.name,
			"actual_start": f"{day} 09:05:00",
			"actual_end": f"{day} 10:50:00",
			"work_performed": "Inspected kitchens; applied gel bait at 12 points.",
			"follow_up_notes": "Re-inspect in 14 days.",
			"materials_used": [{"item_code": base.item, "qty": 2, "uom": "Nos"}],
		}
	).insert()
	report.submit()
	frappe.set_user("Administrator")
	frappe.db.commit()

	schedules = frappe.get_all(
		"Employee Schedule",
		filters={"reference_docname": ("in", [tech, sup])},
		fields=["name", "employee", "start_datetime", "end_datetime"],
	)
	result = {
		"crm_lead": base.lead,
		"service_request": request.name,
		"visit": visit.name,
		"visit_status": frappe.db.get_value("Pest Service Visit", visit.name, "status"),
		"assignments": [tech, sup],
		"onefm_schedules": schedules,
		"completion_report": report.name,
	}
	print(frappe.as_json(result, indent=1))
	return result
