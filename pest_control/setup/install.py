import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from pest_control.constants import PEST_ROLES

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
}


def after_install():
	after_migrate()


def after_migrate():
	for role in PEST_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	create_custom_fields(CUSTOM_FIELDS, update=True)
