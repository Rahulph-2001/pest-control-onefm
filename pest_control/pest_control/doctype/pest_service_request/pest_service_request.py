import frappe
from frappe import _
from frappe.model.document import Document

from pest_control.constants import CRM_SOURCE_DOCTYPES
from pest_control.utils import enforce_guarded_fields


class PestServiceRequest(Document):
	def validate(self):
		enforce_guarded_fields(self, {"status": "Open"})
		self.validate_site_customer()
		self.validate_crm_source()

	def validate_site_customer(self):
		site = frappe.db.get_value(
			"Operations Site", self.operations_site, ["pest_customer", "status"], as_dict=True
		)
		if not site:
			frappe.throw(_("OneFM site {0} does not exist.").format(self.operations_site))
		if site.status == "Inactive":
			frappe.throw(_("OneFM site {0} is inactive.").format(self.operations_site))
		if site.pest_customer != self.customer:
			frappe.throw(
				_("OneFM site {0} is not linked to customer {1}. Set the site's Pest Control Customer first.").format(
					self.operations_site, self.customer
				)
			)

	def validate_crm_source(self):
		if self.crm_reference_doctype not in CRM_SOURCE_DOCTYPES:
			frappe.throw(
				_("CRM source must be one of: {0}").format(", ".join(CRM_SOURCE_DOCTYPES))
			)
		if not frappe.db.exists(self.crm_reference_doctype, self.crm_reference_name):
			frappe.throw(
				_("{0} {1} does not exist.").format(_(self.crm_reference_doctype), self.crm_reference_name)
			)
		if self.crm_reference_doctype == "Opportunity":
			party = frappe.db.get_value(
				"Opportunity", self.crm_reference_name, ["opportunity_from", "party_name"], as_dict=True
			)
			if party.opportunity_from == "Customer" and party.party_name != self.customer:
				frappe.throw(
					_("Opportunity {0} belongs to customer {1}, not {2}.").format(
						self.crm_reference_name, party.party_name, self.customer
					)
				)
