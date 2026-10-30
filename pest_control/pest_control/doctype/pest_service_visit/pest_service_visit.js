const ALLOCATION = "pest_control.allocation";

frappe.ui.form.on("Pest Service Visit", {
	setup(frm) {
		frm.set_query("operations_shift", () => ({ filters: { site: frm.doc.operations_site } }));
		for (const field of ["technician_operations_role", "supervisor_operations_role"]) {
			frm.set_query(field, () => ({ filters: { shift: frm.doc.operations_shift } }));
		}
	},

	refresh(frm) {
		if (frm.is_new()) return;
		const status = frm.doc.status;
		const call = (method, args, message) =>
			frappe
				.call({ method: `${ALLOCATION}.${method}`, args, freeze: true })
				.then(() => {
					if (message) frappe.show_alert({ message, indicator: "green" });
					frm.reload_doc();
				});

		frm.add_custom_button(__("Assignments"), () =>
			frappe.set_route("List", "Pest Visit Assignment", { visit: frm.doc.name })
		);

		if (status === "Draft") {
			frm.add_custom_button(__("Schedule"), () => call("schedule_visit", { visit: frm.doc.name }), __("Actions"));
		}

		if (["Draft", "Scheduled"].includes(status)) {
			frm.add_custom_button(
				__("Allocate Staff"),
				() => {
					const d = new frappe.ui.Dialog({
						title: __("Allocate Staff"),
						fields: [
							{ fieldname: "staffing_role", fieldtype: "Select", label: __("Role"), options: "Technician\nSupervisor", reqd: 1 },
							{ fieldname: "employee", fieldtype: "Link", options: "Employee", label: __("Employee"), reqd: 1,
								get_query: () => ({ filters: { status: "Active" } }) },
							{ fieldname: "eligibility", fieldtype: "HTML" },
						],
						primary_action_label: __("Allocate"),
						primary_action(values) {
							call("allocate", { visit: frm.doc.name, ...values }, __("Allocated")).then(() => d.hide());
						},
					});
					const check = () => {
						const { employee, staffing_role } = d.get_values(true);
						if (!employee || !staffing_role) return;
						frappe
							.call("pest_control.eligibility.check_eligibility", { visit: frm.doc.name, employee, staffing_role })
							.then(({ message }) => {
								d.fields_dict.eligibility.$wrapper.html(
									message.length
										? `<div class="text-danger"><ul>${message.map((r) => `<li>${frappe.utils.escape_html(r)}</li>`).join("")}</ul></div>`
										: `<div class="text-success">${__("Eligible")}</div>`
								);
							});
					};
					d.fields_dict.employee.df.onchange = check;
					d.fields_dict.staffing_role.df.onchange = check;
					d.show();
				},
				__("Actions")
			);

			frm.add_custom_button(
				__("Reschedule"),
				() =>
					frappe.prompt(
						[
							{ fieldname: "scheduled_start", fieldtype: "Datetime", label: __("New Start"), reqd: 1, default: frm.doc.scheduled_start },
							{ fieldname: "scheduled_end", fieldtype: "Datetime", label: __("New End"), reqd: 1, default: frm.doc.scheduled_end },
							{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
						],
						(values) => call("reschedule_visit", { visit: frm.doc.name, ...values }, __("Rescheduled")),
						__("Reschedule Visit")
					),
				__("Actions")
			);
		}

		if (status === "Scheduled") {
			frm.add_custom_button(__("Start Visit"), () => call("start_visit", { visit: frm.doc.name }, __("Started")), __("Actions"));
		}

		if (status === "In Progress") {
			frm.add_custom_button(__("Completion Report"), () =>
				frappe.new_doc("Pest Completion Report", { visit: frm.doc.name, actual_start: frm.doc.actual_start })
			);
		}

		if (!["Completed", "Cancelled"].includes(status)) {
			frm.add_custom_button(
				__("Cancel Visit"),
				() =>
					frappe.prompt(
						{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
						({ reason }) => call("cancel_visit", { visit: frm.doc.name, reason }, __("Cancelled")),
						__("Cancel Visit")
					),
				__("Actions")
			);
		}
	},
});
