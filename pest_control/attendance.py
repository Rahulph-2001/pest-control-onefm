"""Mark the crew Present in Frappe HR when a visit is completed.

One Attendance per crew member per day, using the report's actual times and
linked back to the Pest Visit Assignment. If an Attendance already exists for
that employee and date (for example from OneFM's own check-in processing) it is
left alone. A failure for one employee is logged and does not undo the
completed visit; HR can mark that attendance manually.
"""

import frappe
from frappe.utils import get_datetime, getdate, time_diff_in_hours

from pest_control.audit import log_event
from pest_control.constants import ASSIGNMENT_DOCTYPE


def sync_attendance(visit_doc, report):
	day = getdate(report.actual_start)
	hours = round(time_diff_in_hours(report.actual_end, report.actual_start), 2)
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	results = {}

	for a in frappe.get_all(
		ASSIGNMENT_DOCTYPE, filters={"visit": visit_doc.name, "status": "Active"}, fields=["name", "employee"]
	):
		existing = frappe.db.get_value(
			"Attendance", {"employee": a.employee, "attendance_date": day, "docstatus": ("<", 2)}, "name"
		)
		if existing:
			results[a.employee] = f"existing {existing}"
			continue

		savepoint = f"pest_attendance_{frappe.scrub(a.name)}"
		frappe.db.savepoint(savepoint)
		try:
			attendance = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": a.employee,
					"attendance_date": day,
					"status": "Present",
					"company": frappe.db.get_value("Employee", a.employee, "company") or company,
					"in_time": get_datetime(report.actual_start),
					"out_time": get_datetime(report.actual_end),
					"working_hours": hours,
					"operations_shift": visit_doc.operations_shift,
					"site": visit_doc.operations_site,
					"roster_type": "Basic",
					"reference_doctype": ASSIGNMENT_DOCTYPE,
					"reference_docname": a.name,
				}
			)
			attendance.flags.ignore_permissions = True
			attendance.insert(ignore_permissions=True)
			attendance.submit()
			results[a.employee] = attendance.name
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			frappe.clear_messages()
			results[a.employee] = f"failed: {frappe.utils.strip_html(str(e))[:140]}"

	log_event(
		"Attendance Synced",
		"Pest Service Visit",
		visit_doc.name,
		details={"date": str(day), "working_hours": hours, "attendance": results},
	)
	return results
