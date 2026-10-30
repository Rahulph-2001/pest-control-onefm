import frappe
from frappe import _
from frappe.model.document import Document


class PestAuditEvent(Document):
	def before_insert(self):
		if not self.flags.pest_audit_insert:
			frappe.throw(_("Audit events are written by the system only."), frappe.PermissionError)

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Audit events cannot be modified."), frappe.PermissionError)

	def on_trash(self):
		frappe.throw(_("Audit events cannot be deleted."), frappe.PermissionError)
