"""Optional stock transaction acceptance (plan page 6)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, now_datetime, nowdate

from pest_control import allocation
from pest_control.stock import post_material_consumption
from pest_control.tests import fixtures as fx


def stock_qty(item, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))


class StockPosting(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.base = fx.base_records()
		cls.users = fx.users()
		cls.tech = fx.verified_worker("Arun", user_email=cls.users.field)
		cls.warehouse = frappe.db.get_value(
			"Warehouse", {"company": cls.base.company, "is_group": 0, "warehouse_name": "Stores"}
		) or frappe.db.get_value("Warehouse", {"company": cls.base.company, "is_group": 0})
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("pc_stock")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="pc_stock")

	def receive(self, qty):
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": self.base.company,
				"items": [{"item_code": self.base.item, "qty": qty, "t_warehouse": self.warehouse, "basic_rate": 50}],
			}
		)
		entry.insert()
		entry.submit()

	def completed_report(self, day_offset, qty):
		request = fx.service_request(self.base).name
		visit = fx.visit(self.base, request, day_offset=day_offset, technicians=1, supervisors=0).name
		frappe.set_user(self.users.ops)
		allocation.schedule_visit(visit)
		allocation.allocate(visit, self.tech, "Technician")
		allocation.start_visit(visit)
		report = frappe.get_doc(
			{
				"doctype": "Pest Completion Report",
				"visit": visit,
				"actual_start": add_days(now_datetime(), -1),
				"actual_end": now_datetime(),
				"work_performed": "Gel bait applied.",
				"materials_used": [{"item_code": self.base.item, "qty": qty, "uom": "Nos"}],
			}
		).insert()
		report.submit()
		return report.name

	def test_posting_consumes_stock_once(self):
		self.receive(10)
		before = stock_qty(self.base.item, self.warehouse)
		report = self.completed_report(20, qty=3)

		entry = post_material_consumption(report, self.warehouse)
		self.assertEqual(frappe.db.get_value("Stock Entry", entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Stock Entry", entry, "purpose"), "Material Issue")
		self.assertEqual(stock_qty(self.base.item, self.warehouse), before - 3)
		self.assertEqual(frappe.db.get_value("Pest Completion Report", report, "stock_entry"), entry)

		with self.assertRaises(frappe.ValidationError):
			post_material_consumption(report, self.warehouse)
		self.assertEqual(stock_qty(self.base.item, self.warehouse), before - 3)

	def test_insufficient_stock_is_refused_without_side_effects(self):
		available = stock_qty(self.base.item, self.warehouse)
		report = self.completed_report(21, qty=available + 1000)
		with self.assertRaises(frappe.ValidationError):
			post_material_consumption(report, self.warehouse)
		self.assertFalse(frappe.db.get_value("Pest Completion Report", report, "stock_entry"))
		self.assertEqual(stock_qty(self.base.item, self.warehouse), available)

	def test_field_user_cannot_post(self):
		self.receive(5)
		report = self.completed_report(22, qty=1)
		frappe.set_user(self.users.field)
		with self.assertRaises(frappe.PermissionError):
			post_material_consumption(report, self.warehouse)
