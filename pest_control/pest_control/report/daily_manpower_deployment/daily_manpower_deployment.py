"""Who is deployed where on a day, including unfilled crew positions."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from pest_control.constants import SUPERVISOR, TECHNICIAN


def execute(filters=None):
	filters = frappe._dict(filters or {})
	day = getdate(filters.date or nowdate())
	return get_columns(), get_data(day, filters)


def get_columns():
	return [
		{"fieldname": "start", "label": _("Start"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "end", "label": _("End"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "visit", "label": _("Visit"), "fieldtype": "Link", "options": "Pest Service Visit", "width": 140},
		{"fieldname": "visit_status", "label": _("Visit Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
		{"fieldname": "operations_site", "label": _("OneFM Site"), "fieldtype": "Link", "options": "Operations Site", "width": 170},
		{"fieldname": "staffing_role", "label": _("Role"), "fieldtype": "Data", "width": 95},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "employee_schedule", "label": _("OneFM Schedule"), "fieldtype": "Link", "options": "Employee Schedule", "width": 200},
	]


def get_data(day, filters):
	visit_filters = {
		"scheduled_start": ("between", [f"{day} 00:00:00", f"{day} 23:59:59"]),
		"status": ("!=", "Cancelled"),
	}
	if filters.operations_site:
		visit_filters["operations_site"] = filters.operations_site
	if filters.status:
		visit_filters["status"] = filters.status

	visits = frappe.get_list(
		"Pest Service Visit",
		filters=visit_filters,
		fields=["name", "status", "customer", "operations_site", "scheduled_start", "scheduled_end",
			"required_technicians", "required_supervisors"],
		order_by="scheduled_start asc, name asc",
	)
	rows = []
	for v in visits:
		assignments = frappe.get_all(
			"Pest Visit Assignment",
			filters={"visit": v.name, "status": "Active"},
			fields=["staffing_role", "employee", "employee_name", "employee_schedule"],
			order_by="staffing_role desc, creation asc",
		)
		base = {
			"start": v.scheduled_start,
			"end": v.scheduled_end,
			"visit": v.name,
			"visit_status": v.status,
			"customer": v.customer,
			"operations_site": v.operations_site,
		}
		for a in assignments:
			rows.append({**base, **a})
		for role, required in ((SUPERVISOR, v.required_supervisors), (TECHNICIAN, v.required_technicians)):
			missing = (required or 0) - sum(1 for a in assignments if a.staffing_role == role)
			for _i in range(max(missing, 0)):
				rows.append({**base, "staffing_role": role, "employee_name": _("Unfilled")})
	return rows
