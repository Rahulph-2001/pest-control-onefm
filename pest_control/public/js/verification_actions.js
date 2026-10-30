// Verify / Reject / Revoke buttons shared by the two HR verification forms.
frappe.provide("pest_control");

pest_control.add_verification_actions = (frm) => {
	if (frm.is_new() || !frappe.user.has_role(["Pest HR Verifier", "System Manager"])) return;

	const decide = (decision, reason) =>
		frappe
			.call({
				method: "pest_control.verification.decide",
				args: { doctype: frm.doctype, name: frm.doc.name, decision, reason },
				freeze: true,
			})
			.then(() => frm.reload_doc());

	const withReason = (decision, required) =>
		frappe.prompt(
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: required },
			({ reason }) => decide(decision, reason),
			__(decision)
		);

	const status = frm.doc.verification_status;
	if (["Pending", "Rejected", "Revoked"].includes(status)) {
		frm.add_custom_button(__("Verify"), () => withReason("Verified", 0), __("Decision"));
	}
	if (status === "Pending") {
		frm.add_custom_button(__("Reject"), () => withReason("Rejected", 1), __("Decision"));
	}
	if (status === "Verified") {
		frm.add_custom_button(__("Revoke"), () => withReason("Revoked", 1), __("Decision"));
	}
};

for (const doctype of ["Pest Employee Verification", "Pest Employee Qualification"]) {
	frappe.ui.form.on(doctype, { refresh: pest_control.add_verification_actions });
}
