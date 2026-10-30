import frappe
from frappe.utils import now_datetime

VERIFICATION_DOCTYPES = ("Pest Employee Verification", "Pest Employee Qualification", "Employee")


def log_event(event_type: str, reference_doctype: str, reference_name: str, reason: str | None = None, details=None):
	"""Append an immutable audit record. Runs inside the caller's transaction, so the
	event is rolled back together with the change it describes."""
	category = "Verification" if reference_doctype in VERIFICATION_DOCTYPES else "Operations"
	event = frappe.get_doc(
		{
			"doctype": "Pest Audit Event",
			"event_type": event_type,
			"event_category": category,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"actor": frappe.session.user,
			"event_time": now_datetime(),
			"reason": reason,
			"details": frappe.as_json(details or {}, indent=1),
		}
	)
	event.flags.pest_audit_insert = True
	event.insert(ignore_permissions=True)
	return event.name


def employee_on_update(doc, method=None):
	"""HR status changes affect eligibility; record them for manual review."""
	before = doc.get_doc_before_save()
	if not before or before.status == doc.status:
		return
	log_event(
		"Employee Status Changed",
		"Employee",
		doc.name,
		details={"from": before.status, "to": doc.status},
	)
