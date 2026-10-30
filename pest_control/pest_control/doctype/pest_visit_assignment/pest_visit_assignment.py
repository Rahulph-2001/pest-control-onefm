import frappe
from frappe import _
from frappe.model.document import Document

from pest_control.utils import in_service_write


class PestVisitAssignment(Document):
	"""Links a visit staffing slot to its OneFM Employee Schedule.

	The schedule holds the employee and times; this record only adds the
	staffing role and the replacement/cancellation history. It is written
	exclusively by pest_control.allocation.
	"""

	def validate(self):
		if not in_service_write():
			frappe.throw(
				_("Assignments are managed through the visit's Allocate, Replace and Cancel actions."),
				frappe.PermissionError,
			)

	def on_trash(self):
		frappe.throw(_("Assignment history cannot be deleted."), frappe.PermissionError)
