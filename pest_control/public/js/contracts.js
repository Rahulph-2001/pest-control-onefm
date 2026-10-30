frappe.ui.form.on("Contracts", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.pest_contract_type) return;
		frm.add_custom_button(__("Service Requests"), () =>
			frappe.set_route("List", "Pest Service Request", { contract: frm.doc.name })
		, __("Pest Control"));
		if (!frappe.user.has_role(["Pest Operations Manager", "System Manager"])) return;
		frm.add_custom_button(
			__("Generate Service Requests"),
			() =>
				frappe
					.call({
						method: "pest_control.contracts.generate_service_requests",
						args: { contract: frm.doc.name },
						freeze: true,
					})
					.then(({ message }) =>
						frappe.msgprint(
							__("{0} service request(s) created, {1} already existed.", [message.created.length, message.skipped])
						)
					),
			__("Pest Control")
		);
	},
});
