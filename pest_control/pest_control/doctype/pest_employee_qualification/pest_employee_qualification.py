import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from pest_control.verification import VerifiableDocument


class PestEmployeeQualification(VerifiableDocument, Document):
	material_fields = (
		"employee",
		"qualification_type",
		"certificate_number",
		"valid_from",
		"valid_until",
		"evidence",
	)
	evidence_fields = ("evidence",)

	def validate(self):
		if self.valid_until and getdate(self.valid_until) < getdate(self.valid_from):
			frappe.throw(_("Valid Until cannot be before Valid From."))
		if not self.valid_until and frappe.db.get_value(
			"Pest Qualification Type", self.qualification_type, "expiry_required"
		):
			frappe.throw(_("{0} requires an expiry date.").format(self.qualification_type))
		self.validate_verification()

	def on_update(self):
		VerifiableDocument.on_update(self)

	def check_ready_for_verification(self):
		if not self.evidence or not self.certificate_number:
			frappe.throw(_("Certificate number and evidence are required before verifying."))
