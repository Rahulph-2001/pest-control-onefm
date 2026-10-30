from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import get_datetime


@contextmanager
def atomic(name: str):
	"""Run a block under a savepoint so a failure leaves earlier writes in the
	transaction untouched. Web requests already roll back on error; this also
	protects server-side callers and tests that catch the exception."""
	savepoint = f"pest_{name}"
	frappe.db.savepoint(savepoint)
	try:
		yield
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise
	else:
		frappe.db.release_savepoint(savepoint)


@contextmanager
def service_write():
	"""Mark writes made by the pest-control services so guarded documents accept them."""
	previous = frappe.flags.pest_service_write
	frappe.flags.pest_service_write = True
	try:
		yield
	finally:
		frappe.flags.pest_service_write = previous


def in_service_write() -> bool:
	return bool(frappe.flags.pest_service_write)


def enforce_guarded_fields(doc, fields: dict):
	"""Reject client or API attempts to set system-managed fields.

	`fields` maps fieldname -> value a new document must start with. Only the
	pest-control services (see `service_write`) may change these fields.
	"""
	if in_service_write():
		return

	if doc.is_new():
		for fieldname, initial in fields.items():
			value = doc.get(fieldname)
			if value not in (None, "", initial):
				frappe.throw(
					_("{0} is set by the system and cannot be supplied.").format(doc.meta.get_label(fieldname)),
					frappe.PermissionError,
				)
			doc.set(fieldname, initial)
		return

	before = doc.get_doc_before_save()
	if not before:
		return
	for fieldname in fields:
		if (before.get(fieldname) or None) != (doc.get(fieldname) or None):
			frappe.throw(
				_("{0} can only be changed through its action.").format(doc.meta.get_label(fieldname)),
				frappe.PermissionError,
			)


def require_roles(*roles):
	user_roles = set(frappe.get_roles())
	if "System Manager" in user_roles or user_roles.intersection(roles):
		return
	frappe.throw(_("You are not permitted to perform this action."), frappe.PermissionError)


def lock_row(doctype: str, name: str):
	"""Take an exclusive row lock until the transaction ends."""
	if not frappe.db.sql(f"select name from `tab{doctype}` where name=%s for update", name):
		frappe.throw(_("{0} {1} not found").format(_(doctype), name), frappe.DoesNotExistError)


def overlaps(start_a, end_a, start_b, end_b) -> bool:
	"""Half-open interval overlap: back-to-back intervals do not overlap."""
	return get_datetime(start_a) < get_datetime(end_b) and get_datetime(start_b) < get_datetime(end_a)


def employee_for_user(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	return frappe.db.get_value("Employee", {"user_id": user}, "name")


def is_private_file(file_url: str | None) -> bool:
	return bool(file_url) and file_url.startswith("/private/files/")
