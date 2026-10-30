import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from pest_control.allocation import complete_visit_from_report
from pest_control.materials import validate_material_rows


class PestCompletionReport(Document):
	def validate(self):
		status = frappe.db.get_value("Pest Service Visit", self.visit, "status")
		if status != "In Progress":
			frappe.throw(_("A report can only be prepared for a visit that is In Progress (this one is {0}).").format(_(status)))
		if get_datetime(self.actual_start) >= get_datetime(self.actual_end):
			frappe.throw(_("Actual start must be before actual end."))
		if get_datetime(self.actual_end) > now_datetime():
			frappe.throw(_("Actual end cannot be in the future."))
		validate_material_rows(self.materials_used, _("Materials Used"))

	def before_submit(self):
		if frappe.db.exists(
			"Pest Completion Report", {"visit": self.visit, "docstatus": 1, "name": ("!=", self.name)}
		):
			frappe.throw(_("Visit {0} already has a submitted completion report.").format(self.visit))

	def on_submit(self):
		complete_visit_from_report(self)

	def on_cancel(self):
		frappe.throw(_("Submitted completion reports cannot be cancelled in this prototype."))
