"""HR verification decisions for employees and their qualifications.

Only a Pest HR Verifier (or System Manager) may decide, nobody may decide on
their own record, and any material change to approved evidence returns the
record to Pending until it is reviewed again.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from pest_control.audit import log_event
from pest_control.constants import HR_VERIFIER
from pest_control.utils import enforce_guarded_fields, is_private_file, require_roles, service_write

DECISION_FIELDS = {
	"verification_status": "Pending",
	"reviewed_by": None,
	"decision_time": None,
	"decision_reason": None,
}

ALLOWED_TRANSITIONS = {
	"Verified": ("Pending", "Rejected", "Revoked"),
	"Rejected": ("Pending",),
	"Revoked": ("Verified",),
}


class VerifiableDocument:
	"""Mixin for documents carrying an HR verification decision."""

	# fields whose change invalidates an approval
	material_fields: tuple = ()
	# private file fields
	evidence_fields: tuple = ()

	def validate_verification(self):
		enforce_guarded_fields(self, DECISION_FIELDS)
		for fieldname in self.evidence_fields:
			if self.get(fieldname) and not is_private_file(self.get(fieldname)):
				frappe.throw(
					_("{0} must be uploaded as a private file.").format(self.meta.get_label(fieldname))
				)
		self._invalidate_on_material_change()

	def _invalidate_on_material_change(self):
		if self.is_new() or self.flags.pest_service_write_decision:
			return
		before = self.get_doc_before_save()
		if not before or before.verification_status not in ("Verified", "Rejected"):
			return
		changed = [f for f in self.material_fields if (before.get(f) or None) != (self.get(f) or None)]
		if not changed:
			return
		self.verification_status = "Pending"
		self.flags.pest_invalidated_fields = changed

	def on_update(self):
		changed = self.flags.pest_invalidated_fields
		if changed:
			self.flags.pest_invalidated_fields = None
			log_event(
				"Verification Invalidated",
				self.doctype,
				self.name,
				reason=_("Material change requires a new review"),
				details={"changed_fields": changed},
			)

	def check_ready_for_verification(self):
		"""Hook for documents to require evidence before they can be Verified."""


@frappe.whitelist(methods=["POST"])
def decide(doctype: str, name: str, decision: str, reason: str | None = None):
	if doctype not in ("Pest Employee Verification", "Pest Employee Qualification"):
		frappe.throw(_("Unsupported document type"))
	require_roles(HR_VERIFIER)

	frappe.db.sql(f"select name from `tab{doctype}` where name=%s for update", name)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")

	if decision not in ALLOWED_TRANSITIONS:
		frappe.throw(_("Unknown decision {0}").format(decision))
	if doc.verification_status not in ALLOWED_TRANSITIONS[decision]:
		frappe.throw(
			_("Cannot move from {0} to {1}.").format(_(doc.verification_status), _(decision))
		)

	reviewer_employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if (doc.employee_user and doc.employee_user == frappe.session.user) or reviewer_employee == doc.employee:
		frappe.throw(_("You cannot decide on your own verification."), frappe.PermissionError)

	reason = (reason or "").strip()
	if decision in ("Rejected", "Revoked") and not reason:
		frappe.throw(_("A reason is required to {0}.").format(_(decision).lower()))
	if decision == "Verified":
		doc.check_ready_for_verification()

	previous = doc.verification_status
	doc.verification_status = decision
	doc.reviewed_by = frappe.session.user
	doc.decision_time = now_datetime()
	doc.decision_reason = reason or None
	doc.flags.pest_service_write_decision = True
	with service_write():
		doc.save()

	log_event(
		f"Verification {decision}",
		doctype,
		name,
		reason=reason,
		details={"employee": doc.employee, "from": previous, "to": decision},
	)
	return doc.verification_status
