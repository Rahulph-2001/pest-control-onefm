"""Crew allocation for pest-control visits, backed by OneFM Employee Schedule.

Each active Pest Visit Assignment owns exactly one OneFM Employee Schedule
(linked both ways through the schedule's reference fields). Every change
locks the visit and the affected employee rows, re-checks eligibility against
current commitments and writes the visit, assignment and schedule changes in
one transaction.
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime

from pest_control.audit import log_event
from pest_control.constants import ASSIGNMENT_DOCTYPE, FIELD_USER, OPERATIONS_MANAGER, SUPERVISOR, TECHNICIAN
from pest_control.eligibility import assert_eligible
from pest_control.utils import atomic, employee_for_user, lock_row, require_roles, service_write

ALLOCATABLE_STATES = ("Draft", "Scheduled")


@contextmanager
def onefm_schedule_write():
	"""Allow writes to pest-linked OneFM schedules (see onefm_integration)."""
	previous = frappe.flags.pest_schedule_write
	frappe.flags.pest_schedule_write = True
	try:
		yield
	finally:
		frappe.flags.pest_schedule_write = previous


# ---------------------------------------------------------------- helpers


def _lock_visit(visit: str):
	lock_row("Pest Service Visit", visit)
	return frappe.get_doc("Pest Service Visit", visit)


def _check_manager(visit_doc):
	require_roles(OPERATIONS_MANAGER)
	visit_doc.check_permission("write")


def _active_assignments(visit: str):
	return frappe.get_all(
		ASSIGNMENT_DOCTYPE,
		filters={"visit": visit, "status": "Active"},
		fields=["name", "employee", "staffing_role", "employee_schedule"],
		order_by="creation asc",
	)


def _required_count(visit_doc, staffing_role):
	return (visit_doc.required_technicians if staffing_role == TECHNICIAN else visit_doc.required_supervisors) or 0


def _operations_role(visit_doc, staffing_role):
	if staffing_role == TECHNICIAN:
		return visit_doc.technician_operations_role
	return visit_doc.supervisor_operations_role


def _check_onefm_day_slot(employee, date, exclude=()):
	"""OneFM keys schedules by employee + date + roster type, so only one Basic
	schedule per employee per day can exist."""
	existing = frappe.db.get_value(
		"Employee Schedule",
		{"employee": employee, "date": date, "roster_type": "Basic", "name": ("not in", list(exclude) or [""])},
		"name",
	)
	if existing:
		frappe.throw(
			_(
				"Employee {0} already has OneFM schedule {1} on {2}. OneFM allows one Basic schedule per employee per day."
			).format(employee, existing, date),
			title=_("Not Eligible"),
		)


def _create_schedule(assignment, visit_doc):
	schedule = frappe.get_doc(
		{
			"doctype": "Employee Schedule",
			"employee": assignment.employee,
			"date": getdate(visit_doc.scheduled_start),
			"shift": visit_doc.operations_shift,
			"operations_role": _operations_role(visit_doc, assignment.staffing_role),
			"employee_availability": "Working",
			"roster_type": "Basic",
			"reference_doctype": ASSIGNMENT_DOCTYPE,
			"reference_docname": assignment.name,
		}
	)
	with onefm_schedule_write():
		schedule.insert(ignore_permissions=True)
	return schedule.name


def _release_schedule(schedule_name):
	if schedule_name and frappe.db.exists("Employee Schedule", schedule_name):
		with onefm_schedule_write():
			frappe.delete_doc("Employee Schedule", schedule_name, ignore_permissions=True, force=True)


def _update_coverage(visit_doc):
	active = _active_assignments(visit_doc.name)
	techs = sum(1 for a in active if a.staffing_role == TECHNICIAN)
	sups = sum(1 for a in active if a.staffing_role == SUPERVISOR)
	summary = _("Technicians {0}/{1}, Supervisors {2}/{3}").format(
		techs, visit_doc.required_technicians or 0, sups, visit_doc.required_supervisors or 0
	)
	fully_staffed = int(
		techs >= (visit_doc.required_technicians or 0) and sups >= (visit_doc.required_supervisors or 0)
	)
	frappe.db.set_value(
		"Pest Service Visit",
		visit_doc.name,
		{"coverage_summary": summary, "fully_staffed": fully_staffed},
		update_modified=False,
	)
	return techs, sups


def _set_visit_status(visit_doc, status, reason=None, **values):
	previous = visit_doc.status
	visit_doc.status = status
	visit_doc.status_reason = reason
	for key, value in values.items():
		visit_doc.set(key, value)
	with service_write():
		visit_doc.save(ignore_permissions=True)
	log_event(
		"Visit Status Changed",
		"Pest Service Visit",
		visit_doc.name,
		reason=reason,
		details={"from": previous, "to": status, **{k: str(v) for k, v in values.items()}},
	)
	sync_request_status(visit_doc.service_request)


def sync_request_status(request: str):
	statuses = set(frappe.get_all("Pest Service Visit", filters={"service_request": request}, pluck="status"))
	if statuses & {"Scheduled", "In Progress"}:
		status = "Scheduled"
	elif "Completed" in statuses and not statuses & {"Draft"}:
		status = "Completed"
	else:
		status = "Open"
	if frappe.db.get_value("Pest Service Request", request, "status") != status:
		frappe.db.set_value("Pest Service Request", request, "status", status)


def _end_assignment(assignment_name, status, reason, replaced_by=None):
	doc = frappe.get_doc(ASSIGNMENT_DOCTYPE, assignment_name)
	if doc.status != "Active":
		frappe.throw(_("Assignment {0} is already {1}.").format(doc.name, _(doc.status)))
	released = doc.employee_schedule
	doc.status = status
	doc.end_reason = reason
	doc.ended_by = frappe.session.user
	doc.ended_on = now_datetime()
	doc.replaced_by = replaced_by
	doc.released_employee_schedule = released
	doc.employee_schedule = None
	with service_write():
		doc.save(ignore_permissions=True)
	_release_schedule(released)
	log_event(
		f"Assignment {status}",
		ASSIGNMENT_DOCTYPE,
		doc.name,
		reason=reason,
		details={"visit": doc.visit, "employee": doc.employee, "released_schedule": released},
	)
	return doc


def _allocate(visit_doc, employee, staffing_role, replaces=None):
	if staffing_role not in (TECHNICIAN, SUPERVISOR):
		frappe.throw(_("Staffing role must be Technician or Supervisor."))
	if visit_doc.status not in ALLOCATABLE_STATES:
		frappe.throw(_("Staff cannot be allocated to a {0} visit.").format(_(visit_doc.status)))

	lock_row("Employee", employee)
	active = _active_assignments(visit_doc.name)
	if any(a.employee == employee for a in active):
		frappe.throw(_("Employee {0} is already assigned to this visit.").format(employee))
	if sum(1 for a in active if a.staffing_role == staffing_role) >= _required_count(visit_doc, staffing_role):
		frappe.throw(_("All {0} positions on this visit are filled.").format(_(staffing_role)))

	assert_eligible(
		employee,
		staffing_role,
		visit_doc.scheduled_start,
		visit_doc.scheduled_end,
		visit_doc.required_qualification,
		lock=True,
	)
	_check_onefm_day_slot(employee, getdate(visit_doc.scheduled_start))

	assignment = frappe.get_doc(
		{
			"doctype": ASSIGNMENT_DOCTYPE,
			"visit": visit_doc.name,
			"staffing_role": staffing_role,
			"employee": employee,
			"status": "Active",
			"replaces": replaces,
		}
	)
	with service_write():
		assignment.insert(ignore_permissions=True)
		assignment.employee_schedule = _create_schedule(assignment, visit_doc)
		assignment.save(ignore_permissions=True)

	log_event(
		"Assignment Created",
		ASSIGNMENT_DOCTYPE,
		assignment.name,
		details={
			"visit": visit_doc.name,
			"employee": employee,
			"staffing_role": staffing_role,
			"employee_schedule": assignment.employee_schedule,
			"replaces": replaces,
		},
	)
	return assignment


# ---------------------------------------------------------------- actions


@frappe.whitelist(methods=["POST"])
def allocate(visit: str, employee: str, staffing_role: str):
	with atomic("allocate"):
		visit_doc = _lock_visit(visit)
		_check_manager(visit_doc)
		assignment = _allocate(visit_doc, employee, staffing_role)
		_update_coverage(visit_doc)
	return assignment.name


@frappe.whitelist(methods=["POST"])
def cancel_assignment(assignment: str, reason: str):
	if not (reason or "").strip():
		frappe.throw(_("A reason is required."))
	visit = frappe.db.get_value(ASSIGNMENT_DOCTYPE, assignment, "visit")
	with atomic("cancel_assignment"):
		visit_doc = _lock_visit(visit)
		_check_manager(visit_doc)
		if visit_doc.status not in ALLOCATABLE_STATES:
			frappe.throw(_("Staff on a {0} visit cannot be changed.").format(_(visit_doc.status)))
		_end_assignment(assignment, "Cancelled", reason.strip())
		_update_coverage(visit_doc)


@frappe.whitelist(methods=["POST"])
def replace_assignment(assignment: str, employee: str, reason: str):
	"""Cancel one worker and allocate another in a single transaction; if the
	new worker is not eligible nothing changes."""
	if not (reason or "").strip():
		frappe.throw(_("A reason is required."))
	old = frappe.db.get_value(ASSIGNMENT_DOCTYPE, assignment, ["visit", "staffing_role"], as_dict=True)
	with atomic("replace_assignment"):
		visit_doc = _lock_visit(old.visit)
		_check_manager(visit_doc)
		if visit_doc.status not in ALLOCATABLE_STATES:
			frappe.throw(_("Staff on a {0} visit cannot be changed.").format(_(visit_doc.status)))
		_end_assignment(assignment, "Replaced", reason.strip())
		new = _allocate(visit_doc, employee, old.staffing_role, replaces=assignment)
		frappe.db.set_value(ASSIGNMENT_DOCTYPE, assignment, "replaced_by", new.name, update_modified=False)
		_update_coverage(visit_doc)
	return new.name


@frappe.whitelist(methods=["POST"])
def reschedule_visit(visit: str, scheduled_start: str, scheduled_end: str, reason: str):
	"""Move a visit and every linked OneFM schedule. Idempotent: repeating the
	same request is a no-op. On any failure the original schedule is kept."""
	if not (reason or "").strip():
		frappe.throw(_("A reason is required."))
	new_start, new_end = get_datetime(scheduled_start), get_datetime(scheduled_end)
	if new_start >= new_end:
		frappe.throw(_("Scheduled start must be before scheduled end."))

	with atomic("reschedule"):
		visit_doc = _lock_visit(visit)
		_check_manager(visit_doc)
		if visit_doc.status not in ALLOCATABLE_STATES:
			frappe.throw(_("A {0} visit cannot be rescheduled.").format(_(visit_doc.status)))
		old_start, old_end = get_datetime(visit_doc.scheduled_start), get_datetime(visit_doc.scheduled_end)
		if (old_start, old_end) == (new_start, new_end):
			return {"changed": False}

		active = _active_assignments(visit)
		for a in sorted(active, key=lambda a: a.employee):
			lock_row("Employee", a.employee)
		for a in active:
			assert_eligible(
				a.employee, a.staffing_role, new_start, new_end,
				visit_doc.required_qualification, exclude_schedules=[a.employee_schedule], lock=True,
			)
			_check_onefm_day_slot(a.employee, getdate(new_start), exclude=[a.employee_schedule])

		visit_doc.scheduled_start = new_start
		visit_doc.scheduled_end = new_end
		visit_doc.status_reason = reason.strip()
		with service_write():
			visit_doc.save(ignore_permissions=True)

		moved = {}
		for a in active:
			_release_schedule(a.employee_schedule)
			assignment = frappe.get_doc(ASSIGNMENT_DOCTYPE, a.name)
			assignment.employee_schedule = _create_schedule(assignment, visit_doc)
			with service_write():
				assignment.save(ignore_permissions=True)
			moved[a.name] = {"from": a.employee_schedule, "to": assignment.employee_schedule}

		log_event(
			"Visit Rescheduled",
			"Pest Service Visit",
			visit,
			reason=reason.strip(),
			details={
				"from": [str(old_start), str(old_end)],
				"to": [str(new_start), str(new_end)],
				"schedules": moved,
			},
		)
	return {"changed": True}


@frappe.whitelist(methods=["POST"])
def schedule_visit(visit: str):
	with atomic("schedule_visit"):
		visit_doc = _lock_visit(visit)
		_check_manager(visit_doc)
		if visit_doc.status != "Draft":
			frappe.throw(_("Only Draft visits can be scheduled."))
		_set_visit_status(visit_doc, "Scheduled")
		_update_coverage(visit_doc)


@frappe.whitelist(methods=["POST"])
def start_visit(visit: str):
	"""Start gate: full coverage and fresh eligibility for every assigned worker,
	including checks that the OneFM roster still holds each schedule."""
	with atomic("start_visit"):
		visit_doc = _lock_visit(visit)
		_check_can_run_visit(visit_doc)
		if visit_doc.status != "Scheduled":
			frappe.throw(_("Only Scheduled visits can be started."))

		active = _active_assignments(visit)
		techs, sups = _update_coverage(visit_doc)
		if techs < (visit_doc.required_technicians or 0) or sups < (visit_doc.required_supervisors or 0):
			frappe.throw(
				_("Visit is understaffed: {0} of {1} technicians and {2} of {3} supervisors assigned.").format(
					techs, visit_doc.required_technicians or 0, sups, visit_doc.required_supervisors or 0
				),
				title=_("Cannot Start"),
			)

		for a in sorted(active, key=lambda a: a.employee):
			lock_row("Employee", a.employee)
		for a in active:
			_check_roster_matches(a, visit_doc)
			assert_eligible(
				a.employee, a.staffing_role, visit_doc.scheduled_start, visit_doc.scheduled_end,
				visit_doc.required_qualification, exclude_schedules=[a.employee_schedule], lock=True,
			)

		_set_visit_status(visit_doc, "In Progress", actual_start=now_datetime())


def _check_roster_matches(assignment, visit_doc):
	schedule = frappe.db.get_value(
		"Employee Schedule",
		assignment.employee_schedule,
		["employee", "employee_availability", "start_datetime", "end_datetime", "reference_docname"],
		as_dict=True,
	) if assignment.employee_schedule else None
	if not (
		schedule
		and schedule.employee == assignment.employee
		and schedule.employee_availability == "Working"
		and schedule.reference_docname == assignment.name
		and get_datetime(schedule.start_datetime) == get_datetime(visit_doc.scheduled_start)
		and get_datetime(schedule.end_datetime) == get_datetime(visit_doc.scheduled_end)
	):
		frappe.throw(
			_("OneFM schedule for assignment {0} no longer matches the visit. Reallocate before starting.").format(
				assignment.name
			),
			title=_("Cannot Start"),
		)


def _check_can_run_visit(visit_doc):
	"""Operations Managers, or a field user assigned to the visit."""
	roles = set(frappe.get_roles())
	if roles & {"System Manager", OPERATIONS_MANAGER}:
		return
	employee = employee_for_user()
	if FIELD_USER in roles and employee and frappe.db.exists(
		ASSIGNMENT_DOCTYPE, {"visit": visit_doc.name, "employee": employee, "status": "Active"}
	):
		return
	frappe.throw(_("You are not permitted to perform this action."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def cancel_visit(visit: str, reason: str):
	if not (reason or "").strip():
		frappe.throw(_("A reason is required."))
	with atomic("cancel_visit"):
		visit_doc = _lock_visit(visit)
		_check_manager(visit_doc)
		if visit_doc.status in ("Completed", "Cancelled"):
			frappe.throw(_("A {0} visit cannot be cancelled.").format(_(visit_doc.status)))
		for a in _active_assignments(visit):
			_end_assignment(a.name, "Cancelled", _("Visit cancelled: {0}").format(reason.strip()))
		_set_visit_status(visit_doc, "Cancelled", reason=reason.strip())
		_update_coverage(visit_doc)


def complete_visit_from_report(report):
	"""Called when a completion report is submitted."""
	visit_doc = _lock_visit(report.visit)
	_check_can_run_visit(visit_doc)
	if visit_doc.status != "In Progress":
		frappe.throw(_("Only In Progress visits can be completed."))
	_set_visit_status(
		visit_doc,
		"Completed",
		actual_start=report.actual_start,
		actual_end=report.actual_end,
	)

	from pest_control.attendance import sync_attendance

	sync_attendance(visit_doc, report)
