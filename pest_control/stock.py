"""Optional ERPNext stock posting for materials used on a visit.

Creates and submits one standard Stock Entry (Material Issue) per submitted
completion report. Stock balances are only changed through ERPNext's own
document; insufficient stock is refused by ERPNext's negative-stock check.
"""

import frappe
from frappe import _
from frappe.utils import flt

from pest_control.audit import log_event
from pest_control.constants import OPERATIONS_MANAGER
from pest_control.utils import atomic, lock_row, require_roles


@frappe.whitelist(methods=["POST"])
def post_material_consumption(report: str, source_warehouse: str | None = None):
	require_roles(OPERATIONS_MANAGER)
	with atomic("stock_posting"):
		lock_row("Pest Completion Report", report)
		doc = frappe.get_doc("Pest Completion Report", report)
		doc.check_permission("write")

		if doc.docstatus != 1:
			frappe.throw(_("Submit the completion report before posting stock."))
		if doc.stock_entry:
			frappe.throw(
				_("Materials for this report were already posted in Stock Entry {0}.").format(doc.stock_entry),
				title=_("Already Posted"),
			)

		warehouse = source_warehouse or doc.source_warehouse
		if not warehouse:
			frappe.throw(_("Select a source warehouse."))
		company = frappe.db.get_value("Warehouse", warehouse, "company")

		rows = [r for r in doc.materials_used if frappe.db.get_value("Item", r.item_code, "is_stock_item")]
		if not rows:
			frappe.throw(_("No stock items to post on this report."))
		_check_available(rows, warehouse)

		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Issue",
				"purpose": "Material Issue",
				"company": company,
				"from_warehouse": warehouse,
				"remarks": _("Materials used on pest control visit {0} (report {1})").format(doc.visit, doc.name),
				"items": [
					{
						"item_code": r.item_code,
						"qty": flt(r.qty),
						"uom": r.uom,
						"conversion_factor": _conversion_factor(r.item_code, r.uom),
						"s_warehouse": warehouse,
					}
					for r in rows
				],
			}
		)
		entry.insert(ignore_permissions=True)
		entry.submit()

		doc.db_set(
			{"stock_entry": entry.name, "source_warehouse": warehouse, "stock_posting_status": "Posted"}
		)
		log_event(
			"Materials Posted",
			"Pest Completion Report",
			doc.name,
			details={"stock_entry": entry.name, "warehouse": warehouse, "items": [[r.item_code, r.qty, r.uom] for r in rows]},
		)
	return entry.name


def _check_available(rows, warehouse):
	"""Refuse clearly before ERPNext runs. ERPNext's own negative-stock check
	still applies, but with OneFM installed its zero-stock valuation path raises
	a TypeError (OneFM replaces get_valuation_rate_ with an older signature)."""
	needed = {}
	for r in rows:
		needed[r.item_code] = needed.get(r.item_code, 0) + flt(r.qty) * _conversion_factor(r.item_code, r.uom)
	short = []
	for item_code, qty in needed.items():
		available = flt(
			frappe.db.get_value(
				"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty", for_update=True
			)
		)
		if available < qty:
			short.append(_("{0}: need {1}, available {2}").format(item_code, qty, available))
	if short:
		frappe.throw(
			_("Insufficient stock in {0}:").format(warehouse) + "<br>" + "<br>".join(short),
			title=_("Insufficient Stock"),
		)


def _conversion_factor(item_code, uom):
	if uom == frappe.db.get_value("Item", item_code, "stock_uom"):
		return 1
	return flt(
		frappe.db.get_value(
			"UOM Conversion Detail", {"parent": item_code, "parenttype": "Item", "uom": uom}, "conversion_factor"
		)
	) or 1
