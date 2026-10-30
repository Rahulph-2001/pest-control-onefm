import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission

from pest_control.constants import OPERATIONS_MANAGER, PEST_ROLES

CUSTOM_FIELDS = {
	# Reuse OneFM Operations Site as the service location; no second site master.
	"Operations Site": [
		{
			"fieldname": "pest_control_section",
			"fieldtype": "Section Break",
			"label": "Pest Control",
			"insert_after": "operations_site_location",
			"collapsible": 1,
		},
		{
			"fieldname": "pest_customer",
			"fieldtype": "Link",
			"label": "Pest Control Customer",
			"options": "Customer",
			"insert_after": "pest_control_section",
		},
		{
			"fieldname": "pest_control_notes",
			"fieldtype": "Small Text",
			"label": "Pest Control Notes",
			"insert_after": "pest_customer",
		},
	],
	# Reuse OneFM Contracts for AMC / one-time / seasonal pest control contracts.
	"Contracts": [
		{
			"fieldname": "pest_control_section",
			"fieldtype": "Section Break",
			"label": "Pest Control",
			"insert_after": "items",
		},
		{
			"fieldname": "pest_contract_type",
			"fieldtype": "Select",
			"label": "Pest Control Contract Type",
			"options": "\nAMC\nOne-Time\nSeasonal",
			"insert_after": "pest_control_section",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "pest_services",
			"fieldtype": "Table",
			"label": "Pest Control Services",
			"options": "Pest Contract Service",
			"insert_after": "pest_contract_type",
		},
	],
}

# Roles that need to see records owned by other apps.
EXTRA_PERMISSIONS = [
	("Contracts", OPERATIONS_MANAGER),
	("Operations Site", OPERATIONS_MANAGER),
	("Operations Shift", OPERATIONS_MANAGER),
	("Operations Role", OPERATIONS_MANAGER),
]


def after_install():
	after_migrate()


def after_migrate():
	for role in PEST_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	create_custom_fields(CUSTOM_FIELDS, update=True)
	for doctype, role in EXTRA_PERMISSIONS:
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
			add_permission(doctype, role, 0)

	from pest_control.setup.ui import setup_ui

	setup_ui()
