"""Two genuinely concurrent allocations of the same employee.

Each thread has its own database connection and holds its transaction open
for a moment before committing, so the requests really overlap. Exactly one
must succeed. This commits data, so it is a bench command rather than part of
the rolled-back unit test suite:

bench --site pest.localhost execute pest_control.tests.concurrency_check.run
"""

import threading
import time

import frappe
from frappe.utils import add_days, nowdate

from pest_control import allocation
from pest_control.tests import fixtures as fx


def _free_future_day(employee, start=30, span=60):
	for offset in range(start, start + span):
		day = add_days(nowdate(), offset)
		if not frappe.db.exists("Employee Schedule", {"employee": employee, "date": day}):
			return offset
	frappe.throw("No free day for the concurrency check.")


def _setup():
	frappe.set_user("Administrator")
	base = fx.base_records()
	users = fx.users()
	tech = fx.verified_worker("Concurrent")
	offset = _free_future_day(tech)
	request = fx.service_request(base).name
	visits = [
		fx.visit(base, request, day_offset=offset, start="09:00:00", end="11:00:00", technicians=1, supervisors=0).name,
		fx.visit(base, request, day_offset=offset, start="10:00:00", end="12:00:00", technicians=1, supervisors=0).name,
	]
	frappe.db.commit()
	return frappe._dict(site=frappe.local.site, ops=users.ops, tech=tech, visits=visits)


def _worker(ctx, visit, barrier, results):
	frappe.init(site=ctx.site)
	frappe.connect()
	try:
		frappe.set_user(ctx.ops)
		barrier.wait()
		started = time.monotonic()
		try:
			assignment = allocation.allocate(visit, ctx.tech, "Technician")
			time.sleep(1.5)  # keep the transaction (and its row locks) open
			frappe.db.commit()
			results[visit] = {"ok": True, "assignment": assignment}
		except frappe.ValidationError as e:
			frappe.db.rollback()
			results[visit] = {"ok": False, "error": frappe.utils.strip_html(str(e))[:200]}
		results[visit]["seconds"] = round(time.monotonic() - started, 2)
	finally:
		frappe.destroy()


def run():
	ctx = _setup()
	barrier = threading.Barrier(2)
	results = {}
	threads = [threading.Thread(target=_worker, args=(ctx, v, barrier, results)) for v in ctx.visits]
	for t in threads:
		t.start()
	for t in threads:
		t.join()

	frappe.db.rollback()  # fresh snapshot of what the threads committed
	winners = [v for v, r in results.items() if r["ok"]]
	schedules = frappe.get_all(
		"Employee Schedule",
		filters={"employee": ctx.tech, "reference_doctype": "Pest Visit Assignment", "reference_docname": ("in",
			frappe.get_all("Pest Visit Assignment", filters={"visit": ("in", ctx.visits), "status": "Active"}, pluck="name") or [""])},
		pluck="name",
	)
	passed = len(winners) == 1 and len(schedules) == 1

	# clean up: release the winning assignment and cancel both visits
	frappe.set_user("Administrator")
	for visit in ctx.visits:
		allocation.cancel_visit(visit, "Concurrency check cleanup")
	frappe.db.commit()

	report = {"passed": passed, "results": results, "active_schedules_created": len(schedules)}
	print(frappe.as_json(report, indent=1))
	return report
