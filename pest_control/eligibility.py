"""Eligibility rules for assigning an employee to a pest-control visit.

Every rule fails closed: missing verification, qualification or availability
data makes the employee ineligible. All checks run on the server; list
filtering in the UI is only a convenience.
"""

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, to_timedelta

from pest_control.constants import NON_WORKING_AVAILABILITY, SUPERVISOR, TECHNICIAN


def get_ineligibility_reasons(
	employee: str,
	staffing_role: str,
	start,
	end,
	qualification: str | None = None,
	exclude_schedules: list[str] | None = None,
	lock: bool = False,
) -> list[str]:
	start, end = get_datetime(start), get_datetime(end)
	reasons = []
	reasons += _employment_reasons(employee, end)
	reasons += _verification_reasons(employee, staffing_role)
	if qualification:
		reasons += _qualification_reasons(employee, qualification, start, end)
	reasons += _working_period_reasons(employee, start, end)
	reasons += _leave_reasons(employee, start, end)
	reasons += _schedule_conflict_reasons(employee, start, end, exclude_schedules or [], lock)
	return reasons


def assert_eligible(employee, staffing_role, start, end, qualification=None, exclude_schedules=None, lock=False):
	reasons = get_ineligibility_reasons(
		employee, staffing_role, start, end, qualification, exclude_schedules, lock
	)
	if reasons:
		frappe.throw(
			_("Employee {0} cannot be assigned:").format(employee)
			+ "<ul>"
			+ "".join(f"<li>{frappe.utils.escape_html(r)}</li>" for r in reasons)
			+ "</ul>",
			title=_("Not Eligible"),
		)


def _employment_reasons(employee, end):
	emp = frappe.db.get_value("Employee", employee, ["status", "relieving_date"], as_dict=True)
	if not emp:
		return [_("Employee record not found.")]
	reasons = []
	if emp.status != "Active":
		reasons.append(_("Employment status is {0}.").format(emp.status))
	if emp.relieving_date and getdate(emp.relieving_date) < getdate(end):
		reasons.append(_("Employee is relieved on {0}.").format(emp.relieving_date))
	return reasons


def _verification_reasons(employee, staffing_role):
	v = frappe.db.get_value(
		"Pest Employee Verification",
		{"employee": employee},
		["verification_status", "authorized_technician", "authorized_supervisor"],
		as_dict=True,
	)
	if not v:
		return [_("No HR verification record.")]
	reasons = []
	if v.verification_status != "Verified":
		reasons.append(_("HR verification is {0}.").format(_(v.verification_status)))
	authorized = {TECHNICIAN: v.authorized_technician, SUPERVISOR: v.authorized_supervisor}.get(staffing_role)
	if not authorized:
		reasons.append(_("Not authorized to work as {0}.").format(_(staffing_role)))
	return reasons


def _qualification_reasons(employee, qualification, start, end):
	rows = frappe.get_all(
		"Pest Employee Qualification",
		filters={"employee": employee, "qualification_type": qualification},
		fields=["verification_status", "valid_from", "valid_until"],
	)
	if not rows:
		return [_("Missing required qualification {0}.").format(qualification)]
	for row in rows:
		if (
			row.verification_status == "Verified"
			and getdate(row.valid_from) <= getdate(start)
			and (row.valid_until is None or getdate(row.valid_until) >= getdate(end))
		):
			return []
	statuses = {r.verification_status for r in rows}
	if "Verified" in statuses:
		return [_("Qualification {0} is not valid through the end of the visit.").format(qualification)]
	return [_("Qualification {0} is not verified.").format(qualification)]


def _working_period_reasons(employee, start, end):
	"""Availability is an explicit HR working period: an active, submitted Shift
	Assignment whose Shift Type window covers the whole visit."""
	assignments = frappe.db.sql(
		"""
		select sa.shift_type, st.start_time, st.end_time
		from `tabShift Assignment` sa
		join `tabShift Type` st on st.name = sa.shift_type
		where sa.employee = %(employee)s
			and sa.docstatus = 1 and sa.status = 'Active'
			and sa.start_date <= %(end_date)s
			and (sa.end_date is null or sa.end_date >= %(start_date)s)
		""",
		{"employee": employee, "start_date": getdate(start), "end_date": getdate(end)},
		as_dict=True,
	)
	for a in assignments:
		for day in (add_days(getdate(start), -1), getdate(start)):
			window_start, window_end = _shift_window(day, a.start_time, a.end_time)
			if window_start <= start and end <= window_end:
				return []
	if not assignments:
		return [_("No active working period (Shift Assignment) covers the visit.")]
	return [_("The visit falls outside the employee's working hours.")]


def _shift_window(day, start_time, end_time) -> tuple[datetime, datetime]:
	base = datetime.combine(getdate(day), datetime.min.time())
	window_start = base + to_timedelta(start_time)
	window_end = base + to_timedelta(end_time)
	if window_end <= window_start:
		window_end += timedelta(days=1)
	return window_start, window_end


def _leave_reasons(employee, start, end):
	leave = frappe.db.get_value(
		"Leave Application",
		{
			"employee": employee,
			"docstatus": 1,
			"status": "Approved",
			"from_date": ("<=", getdate(end)),
			"to_date": (">=", getdate(start)),
		},
		["name", "leave_type"],
		as_dict=True,
	)
	if leave:
		return [_("On approved {0} ({1}).").format(leave.leave_type, leave.name)]
	return []


def _schedule_conflict_reasons(employee, start, end, exclude, lock):
	"""Conflicts against every OneFM Employee Schedule of the employee, not only
	pest-control ones. `lock` turns the reads into locking reads so a competing
	transaction's committed schedule is seen after the employee row lock."""
	params = {
		"employee": employee,
		"start": start,
		"end": end,
		"start_date": getdate(start),
		"end_date": getdate(end),
		"exclude": tuple(exclude) or ("",),
		"non_working": NON_WORKING_AVAILABILITY,
	}
	for_update = " for update" if lock else ""
	rows = frappe.db.sql(
		f"""
		select name, date, employee_availability, start_datetime, end_datetime
		from `tabEmployee Schedule`
		where employee = %(employee)s
			and name not in %(exclude)s
			and (
				(employee_availability = 'Working'
					and start_datetime < %(end)s and end_datetime > %(start)s)
				or (employee_availability = 'Working'
					and (start_datetime is null or end_datetime is null)
					and date between %(start_date)s and %(end_date)s)
				or (employee_availability in %(non_working)s
					and date between %(start_date)s and %(end_date)s)
			)
		{for_update}
		""",
		params,
		as_dict=True,
	)
	reasons = []
	for r in rows:
		if r.employee_availability == "Working" and r.start_datetime:
			reasons.append(
				_("Overlaps OneFM schedule {0} ({1} to {2}).").format(r.name, r.start_datetime, r.end_datetime)
			)
		elif r.employee_availability == "Working":
			reasons.append(_("OneFM schedule {0} on {1} has no times; cannot confirm availability.").format(r.name, r.date))
		else:
			reasons.append(_("OneFM roster marks {0} on {1} ({2}).").format(_(r.employee_availability), r.date, r.name))
	return reasons


@frappe.whitelist()
def check_eligibility(visit: str, employee: str, staffing_role: str):
	"""Eligibility result for Operations Managers without exposing HR evidence."""
	visit_doc = frappe.get_doc("Pest Service Visit", visit)
	visit_doc.check_permission("write")
	current = frappe.get_all(
		"Pest Visit Assignment",
		filters={"visit": visit, "employee": employee, "status": "Active"},
		pluck="employee_schedule",
	)
	return get_ineligibility_reasons(
		employee,
		staffing_role,
		visit_doc.scheduled_start,
		visit_doc.scheduled_end,
		visit_doc.required_qualification,
		exclude_schedules=[s for s in current if s],
	)
