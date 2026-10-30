frappe.query_reports["Daily Manpower Deployment"] = {
	filters: [
		{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "operations_site", label: __("OneFM Site"), fieldtype: "Link", options: "Operations Site" },
		{
			fieldname: "status",
			label: __("Visit Status"),
			fieldtype: "Select",
			options: "\nDraft\nScheduled\nIn Progress\nCompleted",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "employee_name" && data && !data.employee) {
			value = `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
