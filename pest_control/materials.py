import frappe
from frappe import _
from frappe.utils import flt


def validate_material_rows(rows, label: str):
	"""Each row must reference an ERPNext Item with a positive quantity in a unit
	that Item supports (its stock UOM or a configured conversion)."""
	for row in rows:
		if flt(row.qty) <= 0:
			frappe.throw(_("{0} row {1}: quantity must be greater than zero.").format(label, row.idx))
		item = frappe.db.get_value("Item", row.item_code, ["stock_uom", "disabled"], as_dict=True)
		if not item:
			frappe.throw(_("{0} row {1}: Item {2} does not exist.").format(label, row.idx, row.item_code))
		if item.disabled:
			frappe.throw(_("{0} row {1}: Item {2} is disabled.").format(label, row.idx, row.item_code))
		if row.uom != item.stock_uom and not frappe.db.exists(
			"UOM Conversion Detail", {"parent": row.item_code, "parenttype": "Item", "uom": row.uom}
		):
			frappe.throw(
				_("{0} row {1}: {2} is not a valid unit for Item {3}.").format(
					label, row.idx, row.uom, row.item_code
				)
			)
