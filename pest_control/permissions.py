"""Record-level access. Role permissions decide *what* a role may do; these
hooks narrow field users to the visits they are assigned to and keep
verification audit events away from operations staff."""

import frappe

from pest_control.constants import HR_VERIFIER, OPERATIONS_MANAGER
from pest_control.utils import employee_for_user

MANAGERS = {"System Manager", OPERATIONS_MANAGER}


def _roles(user):
	return set(frappe.get_roles(user))


def _assigned_visits_sql(employee):
	return (
		"select visit from `tabPest Visit Assignment` "
		f"where employee = {frappe.db.escape(employee)} and status = 'Active'"
	)


def _is_assigned(visit, user):
	employee = employee_for_user(user)
	return bool(
		employee
		and frappe.db.exists("Pest Visit Assignment", {"visit": visit, "employee": employee, "status": "Active"})
	)


def visit_query(user=None):
	user = user or frappe.session.user
	if _roles(user) & MANAGERS:
		return ""
	employee = employee_for_user(user)
	if not employee:
		return "1=0"
	return f"`tabPest Service Visit`.name in ({_assigned_visits_sql(employee)})"


def visit_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _roles(user) & MANAGERS:
		return True
	return _is_assigned(doc.name, user)


def assignment_query(user=None):
	user = user or frappe.session.user
	if _roles(user) & MANAGERS:
		return ""
	employee = employee_for_user(user)
	if not employee:
		return "1=0"
	return f"`tabPest Visit Assignment`.employee = {frappe.db.escape(employee)}"


def assignment_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _roles(user) & MANAGERS:
		return True
	return doc.employee == employee_for_user(user)


def completion_report_query(user=None):
	user = user or frappe.session.user
	if _roles(user) & MANAGERS:
		return ""
	employee = employee_for_user(user)
	if not employee:
		return "1=0"
	return f"`tabPest Completion Report`.visit in ({_assigned_visits_sql(employee)})"


def completion_report_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _roles(user) & MANAGERS:
		return True
	return bool(doc.visit) and _is_assigned(doc.visit, user)


def audit_event_query(user=None):
	user = user or frappe.session.user
	roles = _roles(user)
	if roles & {"System Manager", HR_VERIFIER}:
		return ""
	return "`tabPest Audit Event`.event_category = 'Operations'"


def audit_event_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if ptype not in (None, "read", "report", "print", "export"):
		return False
	roles = _roles(user)
	if roles & {"System Manager", HR_VERIFIER}:
		return True
	return doc.event_category == "Operations"
