frappe.ui.form.on("Pest Completion Report", {
	refresh(frm) {
		if (
			frm.doc.docstatus !== 1 ||
			frm.doc.stock_entry ||
			!frappe.user.has_role(["Pest Operations Manager", "System Manager"])
		) {
			return;
		}
		frm.add_custom_button(__("Post Material Consumption"), () =>
			frappe.prompt(
				{
					fieldname: "source_warehouse",
					fieldtype: "Link",
					options: "Warehouse",
					label: __("Source Warehouse"),
					reqd: 1,
					default: frm.doc.source_warehouse,
					get_query: () => ({ filters: { is_group: 0 } }),
				},
				({ source_warehouse }) =>
					frappe
						.call({
							method: "pest_control.stock.post_material_consumption",
							args: { report: frm.doc.name, source_warehouse },
							freeze: true,
						})
						.then(() => frm.reload_doc()),
				__("Post Material Consumption")
			)
		);
	},
});
