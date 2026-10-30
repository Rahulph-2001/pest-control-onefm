"""Fictional demo/test records. Every helper is idempotent."""

import frappe
from frappe.utils import add_days, getdate, nowdate

from pest_control.allocation import service_write
from pest_control.constants import FIELD_USER, HR_VERIFIER, OPERATIONS_MANAGER

PREFIX = "_PC"
QUALIFICATION = f"{PREFIX} Pesticide Applicator Licence"
SHIFT_TYPE = f"{PREFIX} Day 07-19"


def company():
	name = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value(
		"Company", {}, "name"
	)
	if not name:
		raise RuntimeError("Complete the ERPNext setup wizard (a Company is required) before running tests.")
	return name


def ensure(doctype, filters, values=None, **insert_kwargs):
	name = frappe.db.get_value(doctype, filters, "name")
	if name:
		return frappe.get_doc(doctype, name)
	doc = frappe.get_doc({"doctype": doctype, **filters, **(values or {})})
	fill_mandatory(doc)
	doc.insert(ignore_permissions=True, **insert_kwargs)
	return doc


def fill_mandatory(doc, depth=0):
	"""OneFM adds many mandatory custom fields to standard DocTypes (Arabic names,
	civil IDs, ...). Fill any still-empty required field with fictional data,
	creating a placeholder record when a required link has nothing to point to."""
	for df in doc.meta.get("fields", {"reqd": 1}):
		if doc.get(df.fieldname) not in (None, ""):
			continue
		if df.fieldtype in ("Data", "Small Text", "Text", "Long Text", "Text Editor"):
			value = f"{PREFIX} {df.label or df.fieldname}"
			if df.options == "Email":
				value = f"{frappe.scrub(df.fieldname)}{PREFIX.lower()}@example.com"
			elif df.options == "Phone":
				value = "+919000000000"
			doc.set(df.fieldname, value[: df.length or 140])
		elif df.fieldtype in ("Int", "Float", "Currency", "Percent"):
			doc.set(df.fieldname, 1)
		elif df.fieldtype == "Date":
			doc.set(df.fieldname, nowdate())
		elif df.fieldtype == "Select" and df.options:
			options = [o for o in df.options.split("\n") if o]
			doc.set(df.fieldname, options[0] if options else None)
		elif df.fieldtype == "Link" and df.options:
			filters = {"is_group": 0} if frappe.get_meta(df.options).has_field("is_group") else {}
			value = frappe.db.get_value(df.options, filters, "name")
			if not value and depth < 2 and df.options != doc.doctype:
				placeholder = frappe.get_doc({"doctype": df.options})
				fill_mandatory(placeholder, depth + 1)
				placeholder.insert(ignore_permissions=True, set_name=f"{PREFIX} {df.options}")
				value = placeholder.name
			doc.set(df.fieldname, value)


def user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc("User", email)
	doc.add_roles(*roles)
	return email


def base_records():
	"""Customer, item, shift type, OneFM project/site/shift/roles."""
	comp = company()
	customer_defaults = {
		"customer_type": "Company",
		"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
		"territory": frappe.db.get_value("Territory", {"is_group": 0}),
	}
	customer = ensure("Customer", {"customer_name": f"{PREFIX} Green Valley Apartments"}, customer_defaults).name
	other_customer = ensure("Customer", {"customer_name": f"{PREFIX} Other Customer"}, customer_defaults).name

	ensure("UOM", {"uom_name": "Litre"})
	item = ensure(
		"Item",
		{"item_code": f"{PREFIX}-GEL-BAIT"},
		{"item_name": "Cockroach Gel Bait", "item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 1},
	).name
	service_item = ensure(
		"Item",
		{"item_code": f"{PREFIX}-PEST-SERVICE"},
		{"item_name": "Pest Control Service", "item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 0},
	).name

	ensure("Shift Type", {"name": SHIFT_TYPE}, {"start_time": "07:00:00", "end_time": "19:00:00"}, set_name=SHIFT_TYPE)
	ensure("Pest Qualification Type", {"qualification_name": QUALIFICATION}, {"expiry_required": 1})

	project = ensure(
		"Project",
		{"project_name": f"{PREFIX} Pest Control Contracts"},
		{"company": comp, "status": "Open", "is_active": "Yes"},
	).name
	contact = ensure("Contact", {"first_name": f"{PREFIX} Site Manager"}).name
	location = ensure(
		"Location", {"location_name": f"{PREFIX} Green Valley"}, {"latitude": 12.97, "longitude": 77.59}
	).name
	site = ensure(
		"Operations Site",
		{"site_name": f"{PREFIX} Green Valley Block A"},
		{
			"project": project,
			"status": "Active",
			"pest_customer": customer,
			"site_location": location,
			"poc": [{"poc": contact, "designation": "Facility Manager"}],
		},
	).name
	service_type = ensure("Service Type", {"service_type": f"{PREFIX} Pest Control"}).name
	shift = ensure(
		"Operations Shift",
		{"site": site, "shift_number": 1},
		{"shift_type": SHIFT_TYPE, "service_type": service_type, "status": "Active"},
	).name
	tech_role = ensure(
		"Operations Role",
		{"post_name": f"{PREFIX} Pest Technician", "shift": shift},
		{"post_abbrv": "PCT", "sale_item": service_item, "status": "Active"},
	).name
	sup_role = ensure(
		"Operations Role",
		{"post_name": f"{PREFIX} Pest Supervisor", "shift": shift},
		{"post_abbrv": "PCS", "sale_item": service_item, "status": "Active"},
	).name

	lead = ensure("Lead", {"lead_name": f"{PREFIX} Green Valley enquiry"}, {"company_name": "Green Valley Apartments"}).name

	return frappe._dict(
		company=comp, customer=customer, other_customer=other_customer, item=item, project=project,
		site=site, shift=shift, tech_role=tech_role, sup_role=sup_role, lead=lead,
	)


def employee(first_name, user_email=None, create_user_permission=1):
	"""Note: OneFM's Employee.on_update commits the transaction (push
	notification), so tests must create employees in setUpClass, not in a test.
	Frappe HR restricts a linked user to their own Employee unless
	create_user_permission is off; HR staff accounts need it off."""
	name = frappe.db.get_value("Employee", {"first_name": first_name, "last_name": PREFIX})
	if not name:
		doc = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": first_name,
				"last_name": PREFIX,
				"gender": "Male",
				"date_of_birth": "1995-01-01",
				"date_of_joining": "2024-01-01",
				"company": company(),
				"status": "Active",
				"user_id": user_email,
				"create_user_permission": create_user_permission,
			}
		)
		fill_mandatory(doc)
		doc.insert(ignore_permissions=True)
		name = doc.name
	return name


def private_file(label):
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{frappe.scrub(label)}.txt",
			"content": f"Fictional evidence: {label}",
			"is_private": 1,
		}
	).insert(ignore_permissions=True)
	return doc.file_url


def verified_worker(
	first_name, roles=("Technician",), user_email=None, qualified=True, qual_valid_days=365,
	create_user_permission=1,
):
	"""An employee with a Verified HR record, an optional verified qualification
	and an open-ended Shift Assignment (working period)."""
	emp = employee(first_name, user_email, create_user_permission)
	verification = frappe.db.get_value("Pest Employee Verification", {"employee": emp})
	if not verification:
		doc = frappe.get_doc(
			{
				"doctype": "Pest Employee Verification",
				"employee": emp,
				"identity_document_type": "National ID",
				"identity_document_number": f"ID-{first_name}",
				"identity_evidence": private_file(f"{first_name} id"),
				"employment_evidence": private_file(f"{first_name} contract"),
				"right_to_work_evidence": private_file(f"{first_name} permit"),
				"identity_checked": 1,
				"employment_checked": 1,
				"right_to_work_checked": 1,
				"authorized_technician": int("Technician" in roles),
				"authorized_supervisor": int("Supervisor" in roles),
			}
		).insert(ignore_permissions=True)
		_force_status(doc, "Verified")
	if qualified and not frappe.db.exists("Pest Employee Qualification", {"employee": emp}):
		doc = frappe.get_doc(
			{
				"doctype": "Pest Employee Qualification",
				"employee": emp,
				"qualification_type": QUALIFICATION,
				"certificate_number": f"LIC-{first_name}",
				"valid_from": add_days(nowdate(), -30),
				"valid_until": add_days(nowdate(), qual_valid_days),
				"evidence": private_file(f"{first_name} licence"),
			}
		).insert(ignore_permissions=True)
		_force_status(doc, "Verified")
	working_period(emp)
	return emp


def working_period(emp):
	if frappe.db.exists("Shift Assignment", {"employee": emp, "shift_type": SHIFT_TYPE, "docstatus": 1}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Shift Assignment",
			"employee": emp,
			"shift_type": SHIFT_TYPE,
			"company": company(),
			"start_date": add_days(nowdate(), -30),
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()


def _force_status(doc, status):
	"""Seed a decision directly (demo data only; the real path is verification.decide)."""
	doc.verification_status = status
	doc.reviewed_by = "Administrator"
	doc.decision_time = frappe.utils.now_datetime()
	doc.flags.pest_service_write_decision = True
	with service_write():
		doc.save(ignore_permissions=True)


def service_request(base, **overrides):
	values = {
		"doctype": "Pest Service Request",
		"customer": base.customer,
		"operations_site": base.site,
		"pest_category": "Cockroaches",
		"requested_date": nowdate(),
		"crm_reference_doctype": "Lead",
		"crm_reference_name": base.lead,
		"description": "Cockroach activity in kitchen areas of Block A.",
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def visit(base, request, day_offset=1, start="09:00:00", end="12:00:00", technicians=2, supervisors=1, **overrides):
	day = getdate(add_days(nowdate(), day_offset))
	values = {
		"doctype": "Pest Service Visit",
		"service_request": request,
		"operations_shift": base.shift,
		"scheduled_start": f"{day} {start}",
		"scheduled_end": f"{day} {end}",
		"required_technicians": technicians,
		"required_supervisors": supervisors,
		"technician_operations_role": base.tech_role,
		"supervisor_operations_role": base.sup_role,
		"required_qualification": QUALIFICATION,
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def users():
	return frappe._dict(
		ops=user(f"ops{PREFIX.lower()}@example.com", [OPERATIONS_MANAGER]),
		hr=user(f"hr{PREFIX.lower()}@example.com", [HR_VERIFIER]),
		field=user(f"field{PREFIX.lower()}@example.com", [FIELD_USER]),
		field2=user(f"field2{PREFIX.lower()}@example.com", [FIELD_USER]),
	)
