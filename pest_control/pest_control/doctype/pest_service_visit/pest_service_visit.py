import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime

from pest_control.materials import validate_material_rows
from pest_control.utils import enforce_guarded_fields, in_service_write

GUARDED = {
	"status": "Draft",
	"actual_start": None,
	"actual_end": None,
	"status_reason": None,
	"coverage_summary": None,
}


class PestServiceVisit(Document):
	def validate(self):
		enforce_guarded_fields(self, GUARDED)
		self.validate_request()
		self.validate_times()
		self.validate_staffing()
		self.validate_roles()
		validate_material_rows(self.planned_materials, _("Planned Materials"))
		self.guard_rescheduling()

	def validate_request(self):
		request = frappe.db.get_value(
			"Pest Service Request",
			self.service_request,
			["customer", "operations_site", "status"],
			as_dict=True,
		)
		if request.status == "Cancelled":
			frappe.throw(_("Service request {0} is cancelled.").format(self.service_request))
		self.customer = request.customer
		self.operations_site = request.operations_site

		shift_site = frappe.db.get_value("Operations Shift", self.operations_shift, "site")
		if shift_site != self.operations_site:
			frappe.throw(
				_("OneFM shift {0} belongs to site {1}, not {2}.").format(
					self.operations_shift, shift_site, self.operations_site
				)
			)

	def validate_times(self):
		if get_datetime(self.scheduled_start) >= get_datetime(self.scheduled_end):
			frappe.throw(_("Scheduled start must be before scheduled end."))

	def validate_staffing(self):
		if (self.required_technicians or 0) < 0 or (self.required_supervisors or 0) < 0:
			frappe.throw(_("Staffing counts cannot be negative."))
		if not (self.required_technicians or self.required_supervisors):
			frappe.throw(_("A visit needs at least one technician or supervisor."))

	def validate_roles(self):
		for fieldname in ("technician_operations_role", "supervisor_operations_role"):
			role = self.get(fieldname)
			if role and frappe.db.get_value("Operations Role", role, "shift") != self.operations_shift:
				frappe.throw(
					_("{0} {1} does not belong to shift {2}.").format(
						self.meta.get_label(fieldname), role, self.operations_shift
					)
				)

	def guard_rescheduling(self):
		"""Times and staffing of an allocated visit change only through the
		reschedule action, which moves the linked OneFM schedules atomically."""
		if self.is_new() or in_service_write():
			return
		before = self.get_doc_before_save()
		locked = ("scheduled_start", "scheduled_end", "operations_shift", "service_request",
			"technician_operations_role", "supervisor_operations_role", "required_qualification")
		def normalized(doc, fieldname):
			value = doc.get(fieldname)
			if value and fieldname in ("scheduled_start", "scheduled_end"):
				return get_datetime(value)
			return value or None

		changed = [f for f in locked if normalized(before, f) != normalized(self, f)]
		if not changed:
			return
		if self.status not in ("Draft", "Scheduled"):
			frappe.throw(_("A visit that is {0} cannot be changed.").format(_(self.status)))
		if frappe.db.exists("Pest Visit Assignment", {"visit": self.name, "status": "Active"}):
			frappe.throw(
				_("This visit has allocated staff. Use Reschedule to change {0}.").format(
					", ".join(self.meta.get_label(f) for f in changed)
				)
			)

	def on_trash(self):
		if frappe.db.exists("Pest Visit Assignment", {"visit": self.name}):
			frappe.throw(_("Visits with assignment history cannot be deleted. Cancel the visit instead."))
