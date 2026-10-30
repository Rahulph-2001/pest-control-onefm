import frappe
from frappe import _
from frappe.model.document import Document

from pest_control.verification import VerifiableDocument


class PestEmployeeVerification(VerifiableDocument, Document):
	material_fields = (
		"employee",
		"identity_document_type",
		"identity_document_number",
		"identity_evidence",
		"employment_evidence",
		"right_to_work_evidence",
		"identity_checked",
		"employment_checked",
		"right_to_work_checked",
		"authorized_technician",
		"authorized_supervisor",
	)
	evidence_fields = ("identity_evidence", "employment_evidence", "right_to_work_evidence")

	def validate(self):
		self.validate_verification()

	def on_update(self):
		VerifiableDocument.on_update(self)

	def check_ready_for_verification(self):
		missing = [
			self.meta.get_label(f)
			for f in (
				"identity_document_type",
				"identity_document_number",
				*self.evidence_fields,
				"identity_checked",
				"employment_checked",
				"right_to_work_checked",
			)
			if not self.get(f)
		]
		if missing:
			frappe.throw(_("Cannot verify until these are complete: {0}").format(", ".join(missing)))
		if not (self.authorized_technician or self.authorized_supervisor):
			frappe.throw(_("Authorize at least one staffing role before verifying."))
