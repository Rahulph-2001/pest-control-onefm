"""Pest-control contracts (AMC, one-time, seasonal) on top of OneFM Contracts.

OneFM's Contracts record holds the commercial terms (client, project, dates,
billing, renewal). pest_control adds the contract type and a services table
(site, pest category, visit frequency). Service requests are generated from it
on demand -- automatic recurring visits stay out of scope -- and an Operations
Manager schedules visits from those requests as usual.
"""

import frappe
from frappe import _
from frappe.utils import add_months, getdate

from pest_control.audit import log_event
from pest_control.constants import OPERATIONS_MANAGER
from pest_control.utils import atomic, lock_row, require_roles

FREQUENCY_MONTHS = {"Monthly": 1, "Bi-Monthly": 2, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}


def service_dates(start, end, frequency):
	start, end = getdate(start), getdate(end)
	if frequency == "One-Time":
		return [start]
	step = FREQUENCY_MONTHS[frequency]
	dates, n = [], 0
	while (day := getdate(add_months(start, n * step))) <= end:
		dates.append(day)
		n += 1
	return dates


@frappe.whitelist(methods=["POST"])
def generate_service_requests(contract: str):
	"""Create the Open service requests a contract calls for. Idempotent: dates
	that already have a request for the same site and pest are skipped."""
	require_roles(OPERATIONS_MANAGER)
	frappe.has_permission("Contracts", "read", contract, throw=True)
	with atomic("contract_requests"):
		lock_row("Contracts", contract)
		doc = frappe.get_doc("Contracts", contract)
		if not doc.get("pest_contract_type"):
			frappe.throw(_("Set the Pest Control Contract Type on {0} first.").format(contract))
		if not (doc.start_date and doc.end_date):
			frappe.throw(_("The contract needs a start and end date."))
		if not doc.get("pest_services"):
			frappe.throw(_("Add at least one pest control service to the contract."))

		created, skipped = [], 0
		for row in doc.pest_services:
			customer = frappe.db.get_value("Operations Site", row.operations_site, "pest_customer")
			if customer != doc.client:
				frappe.throw(
					_("Row {0}: site {1} is not linked to customer {2}.").format(row.idx, row.operations_site, doc.client)
				)
			for day in service_dates(doc.start_date, doc.end_date, row.visit_frequency):
				if frappe.db.exists(
					"Pest Service Request",
					{"contract": contract, "operations_site": row.operations_site,
						"pest_category": row.pest_category, "requested_date": day},
				):
					skipped += 1
					continue
				request = frappe.get_doc(
					{
						"doctype": "Pest Service Request",
						"customer": doc.client,
						"operations_site": row.operations_site,
						"pest_category": row.pest_category,
						"requested_date": day,
						"contract": contract,
						"description": _("{0} {1} service under contract {2}.{3}").format(
							row.visit_frequency, row.pest_category, contract, f" {row.notes}" if row.notes else ""
						),
					}
				)
				request.insert()
				created.append(request.name)

		if created:
			log_event(
				"Contract Requests Generated",
				"Contracts",
				contract,
				details={"created": created, "skipped_existing": skipped},
			)
	return {"created": created, "skipped": skipped}
