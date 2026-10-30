frappe.ui.form.on("Pest Visit Assignment", {
	refresh(frm) {
		if (frm.doc.status !== "Active") return;
		const call = (method, args) =>
			frappe
				.call({ method: `pest_control.allocation.${method}`, args, freeze: true })
				.then(() => frm.reload_doc());

		frm.add_custom_button(__("Replace Worker"), () =>
			frappe.prompt(
				[
					{ fieldname: "employee", fieldtype: "Link", options: "Employee", label: __("New Employee"), reqd: 1 },
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
				],
				(values) => call("replace_assignment", { assignment: frm.doc.name, ...values }),
				__("Replace Worker")
			)
		);
		frm.add_custom_button(__("Cancel Assignment"), () =>
			frappe.prompt(
				{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
				({ reason }) => call("cancel_assignment", { assignment: frm.doc.name, reason }),
				__("Cancel Assignment")
			)
		);
	},
});
