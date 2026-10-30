"""Guards on OneFM Employee Schedule.

Pest-linked schedules (reference_doctype = Pest Visit Assignment) are created,
moved and released only by pest_control.allocation. Native OneFM writes that
go through the document controller (Desk form, imports, REST API, roster tools
that save documents) are checked here so they cannot double-book an employee
who holds pest-control work.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from pest_control.constants import ASSIGNMENT_DOCTYPE, NON_WORKING_AVAILABILITY


def _is_pest(doc) -> bool:
	return doc.get("reference_doctype") == ASSIGNMENT_DOCTYPE


def _service_write() -> bool:
	return bool(frappe.flags.pest_schedule_write)


def employee_schedule_validate(doc, method=None):
	before = None if doc.is_new() else doc.get_doc_before_save()
	if (_is_pest(doc) or (before and _is_pest(before))) and not _service_write():
		frappe.throw(
			_("This schedule belongs to a pest-control visit. Change it from the visit."),
			frappe.PermissionError,
		)

	if _is_pest(doc):
		_apply_visit_times(doc)
		return

	_reject_conflict_with_pest_work(doc)


def employee_schedule_on_trash(doc, method=None):
	if _is_pest(doc) and not _service_write():
		frappe.throw(
			_("This schedule belongs to a pest-control visit. Cancel the assignment from the visit."),
			frappe.PermissionError,
		)


def _apply_visit_times(doc):
	"""OneFM derives start/end from the Shift Type; a pest visit carries its own
	window, so the schedule takes the visit's exact times."""
	visit = frappe.db.get_value(ASSIGNMENT_DOCTYPE, doc.reference_docname, "visit")
	start, end = frappe.db.get_value("Pest Service Visit", visit, ["scheduled_start", "scheduled_end"])
	doc.start_datetime = start
	doc.end_datetime = end
	doc.date = getdate(start)


def _reject_conflict_with_pest_work(doc):
	params = {"employee": doc.employee, "name": doc.name or "", "date": doc.date}
	if doc.employee_availability == "Working" and doc.start_datetime and doc.end_datetime:
		condition = "start_datetime < %(end)s and end_datetime > %(start)s"
		params.update(start=doc.start_datetime, end=doc.end_datetime)
	elif doc.employee_availability in NON_WORKING_AVAILABILITY or doc.employee_availability == "Working":
		condition = "date = %(date)s"
	else:
		return
	conflict = frappe.db.sql(
		f"""
		select name, reference_docname from `tabEmployee Schedule`
		where employee = %(employee)s and name != %(name)s
			and reference_doctype = '{ASSIGNMENT_DOCTYPE}'
			and employee_availability = 'Working'
			and {condition}
		limit 1
		""",
		params,
		as_dict=True,
	)
	if conflict:
		frappe.throw(
			_("Employee {0} has pest-control work in OneFM schedule {1} (assignment {2}) at this time.").format(
				doc.employee, conflict[0].name, conflict[0].reference_docname
			),
			title=_("Schedule Conflict"),
		)
