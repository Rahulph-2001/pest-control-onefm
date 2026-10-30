"""Re-apply OneFM's custom fields one field at a time.

OneFM's after_install creates custom fields per DocType and logs (rather than
raises) any error. On a fresh v15 site, one conflicting field -- e.g. Employee
`iban`, which Frappe HR now ships as a standard field -- aborts every other
OneFM field on that DocType, including ones OneFM's own code depends on
(Employee.project). This applies each field separately and skips only the
genuine conflicts.

bench --site <site> execute pest_control.setup.onefm_repair.repair_custom_fields
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def repair_custom_fields():
	"""Some fields reference others created later in the same batch, so repeat
	until a pass creates nothing new."""
	total = 0
	while True:
		result = _repair_pass()
		total += result["created"]
		if not result["created"]:
			break
	_add_renamed_employee_field()
	_add_employee_schedule_workflow_state()
	print(f"OneFM custom field repair: {total} created in total")
	return {"created": total, "skipped": result["skipped"]}


def _add_renamed_employee_field():
	"""OneFM's Employee code reads `one_fm_fourth_name_in_arabic`, but its custom
	field list still creates `one_fm_forth_name_in_arabic`; the rename patch
	assumes both columns already exist. Without the new field every Employee
	save fails on a fresh site."""
	if frappe.get_meta("Employee").has_field("one_fm_fourth_name_in_arabic"):
		return
	create_custom_field(
		"Employee",
		{
			"fieldname": "one_fm_fourth_name_in_arabic",
			"fieldtype": "Data",
			"label": "Fourth Name in Arabic",
			"insert_after": "one_fm_forth_name_in_arabic",
		},
	)
	frappe.db.commit()
	print("Added Employee.one_fm_fourth_name_in_arabic (OneFM rename gap)")


def _add_employee_schedule_workflow_state():
	"""Employee Schedule's controller reads `workflow_state` on every update, but
	OneFM's workflow for it fails to install on a fresh site (its states are
	missing), so the column is never created."""
	if frappe.db.has_column("Employee Schedule", "workflow_state"):
		return
	create_custom_field(
		"Employee Schedule",
		{
			"fieldname": "workflow_state",
			"fieldtype": "Link",
			"label": "Workflow State",
			"options": "Workflow State",
			"hidden": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
		},
	)
	frappe.db.commit()
	print("Added Employee Schedule.workflow_state (OneFM workflow install gap)")


def _repair_pass():
	from one_fm.setup.custom_field import get_custom_fields

	created, skipped = 0, []
	for doctype, fields in get_custom_fields().items():
		if not frappe.db.exists("DocType", doctype):
			skipped.append(f"{doctype}: DocType not installed")
			continue
		meta = frappe.get_meta(doctype)
		for field in fields:
			fieldname = field.get("fieldname")
			if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}):
				continue
			if meta.has_field(fieldname):
				skipped.append(f"{doctype}.{fieldname}: standard field exists")
				continue
			try:
				create_custom_field(doctype, field, ignore_validate=False)
				created += 1
			except Exception as e:
				frappe.db.rollback()
				skipped.append(f"{doctype}.{fieldname}: {type(e).__name__}: {str(e)[:120]}")
			else:
				frappe.db.commit()

	frappe.clear_cache()
	print(f"Created {created} OneFM custom fields; skipped {len(skipped)}:")
	for line in skipped:
		print("  -", line)
	return {"created": created, "skipped": skipped}
