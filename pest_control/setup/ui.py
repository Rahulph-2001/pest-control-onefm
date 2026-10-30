"""Workspace, dashboard cards/charts and the service certificate print format.

Created (or refreshed) on every migrate. Kept in code rather than exported
JSON so the definitions live in one place.
"""

import json

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from pest_control.constants import FIELD_USER, HR_VERIFIER, OPERATIONS_MANAGER

MODULE = "Pest Control"
VISIT = "Pest Service Visit"

NUMBER_CARDS = [
	{"label": "Pest Visits Today", "document_type": VISIT, "color": "#1d6b57",
		"filters": [[VISIT, "scheduled_start", "Timespan", "today", False], [VISIT, "status", "!=", "Cancelled", False]]},
	{"label": "Pest Visits Scheduled", "document_type": VISIT, "color": "#2b6cb0",
		"filters": [[VISIT, "status", "=", "Scheduled", False]]},
	{"label": "Pest Visits In Progress", "document_type": VISIT, "color": "#b7791f",
		"filters": [[VISIT, "status", "=", "In Progress", False]]},
	{"label": "Pest Understaffed Visits", "document_type": VISIT, "color": "#c53030",
		"filters": [[VISIT, "status", "in", ["Draft", "Scheduled"], False], [VISIT, "fully_staffed", "=", 0, False]]},
	{"label": "Pest Pending Verifications", "document_type": "Pest Employee Verification", "color": "#6b46c1",
		"filters": [["Pest Employee Verification", "verification_status", "=", "Pending", False]]},
	{"label": "Pest Active Contracts", "document_type": "Contracts", "color": "#2f855a",
		"filters": [["Contracts", "pest_contract_type", "is", "set", False]],
		"dynamic_filters": [["Contracts", "end_date", ">=", "frappe.datetime.get_today()"]]},
]

CHARTS = [
	{"chart_name": "Pest Visits by Status", "chart_type": "Group By", "document_type": VISIT,
		"group_by_based_on": "status", "group_by_type": "Count", "type": "Donut"},
	{"chart_name": "Pest Visits per Day", "chart_type": "Count", "document_type": VISIT,
		"based_on": "scheduled_start", "timespan": "Last Month", "time_interval": "Daily", "timeseries": 1, "type": "Bar"},
]

SHORTCUTS = [
	("Service Requests", "DocType", "Pest Service Request"),
	("Visits", "DocType", VISIT),
	("Daily Manpower", "Report", "Daily Manpower Deployment"),
	("OneFM Roster", "DocType", "Employee Schedule"),
]

LINK_CARDS = {
	"Operations": [
		("DocType", "Pest Service Request"), ("DocType", VISIT), ("DocType", "Pest Visit Assignment"),
		("DocType", "Pest Completion Report"), ("Report", "Daily Manpower Deployment"),
	],
	"Contracts and Sites": [
		("DocType", "Contracts"), ("DocType", "Operations Site"), ("DocType", "Customer"), ("DocType", "CRM Lead"),
	],
	"People": [
		("DocType", "Employee"), ("DocType", "Pest Employee Verification"), ("DocType", "Pest Employee Qualification"),
		("DocType", "Pest Qualification Type"), ("DocType", "Employee Schedule"), ("DocType", "Attendance"),
	],
	"Audit": [("DocType", "Pest Audit Event")],
}


def setup_ui():
	previous = frappe.flags.in_patch
	frappe.flags.in_patch = True  # keep developer mode from exporting these as app files
	try:
		_print_format()
		for card in NUMBER_CARDS:
			_number_card(card)
		for chart in CHARTS:
			_chart(chart)
		_workspace()
	finally:
		frappe.flags.in_patch = previous


def _upsert(doctype, name, values):
	doc = frappe.get_doc(doctype, name) if frappe.db.exists(doctype, name) else frappe.new_doc(doctype)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.save() if not doc.is_new() else doc.insert(set_name=name)
	return doc


def _number_card(card):
	_upsert("Number Card", card["label"], {
		"label": card["label"],
		"type": "Document Type",
		"document_type": card["document_type"],
		"function": "Count",
		"filters_json": json.dumps(card["filters"]),
		"dynamic_filters_json": json.dumps(card.get("dynamic_filters", [])),
		"color": card["color"],
		"is_public": 1,
		"is_standard": 0,
		"module": MODULE,
		"show_percentage_stats": 0,
	})


def _chart(chart):
	_upsert("Dashboard Chart", chart["chart_name"], {
		**chart,
		"filters_json": "[]",
		"is_public": 1,
		"is_standard": 0,
		"module": MODULE,
	})


def _workspace():
	content = [{"id": "hdr1", "type": "header", "data": {"text": '<span class="h4"><b>Today</b></span>', "col": 12}}]
	content += [{"id": f"nc{i}", "type": "number_card", "data": {"number_card_name": c["label"], "col": 4}}
		for i, c in enumerate(NUMBER_CARDS)]
	content += [{"id": f"ch{i}", "type": "chart", "data": {"chart_name": c["chart_name"], "col": 6}}
		for i, c in enumerate(CHARTS)]
	content.append({"id": "hdr2", "type": "header", "data": {"text": '<span class="h4"><b>Shortcuts</b></span>', "col": 12}})
	content += [{"id": f"sc{i}", "type": "shortcut", "data": {"shortcut_name": s[0], "col": 3}} for i, s in enumerate(SHORTCUTS)]
	content.append({"id": "hdr3", "type": "header", "data": {"text": '<span class="h4"><b>Records</b></span>', "col": 12}})
	content += [{"id": f"cd{i}", "type": "card", "data": {"card_name": name, "col": 4}} for i, name in enumerate(LINK_CARDS)]

	links = []
	for card, items in LINK_CARDS.items():
		links.append({"type": "Card Break", "label": card, "link_count": len(items)})
		links += [{"type": "Link", "label": target, "link_type": kind, "link_to": target, "is_query_report": 0}
			for kind, target in items]

	values = {
		"label": "Pest Control",
		"title": "Pest Control",
		"module": MODULE,
		"public": 1,
		"icon": "tool",
		"sequence_id": 1,
		"content": json.dumps(content),
		"number_cards": [{"number_card_name": c["label"], "label": c["label"]} for c in NUMBER_CARDS],
		"charts": [{"chart_name": c["chart_name"], "label": c["chart_name"]} for c in CHARTS],
		"shortcuts": [{"label": l, "type": t, "link_to": target, "color": "Grey"} for l, t, target in SHORTCUTS],
		"links": links,
		"roles": [{"role": r} for r in ("System Manager", OPERATIONS_MANAGER, HR_VERIFIER, FIELD_USER)],
	}
	if frappe.db.exists("Workspace", "Pest Control"):
		ws = frappe.get_doc("Workspace", "Pest Control")
		for table in ("number_cards", "charts", "shortcuts", "links", "roles"):
			ws.set(table, [])
		ws.update(values)
		ws.save(ignore_permissions=True)
	else:
		frappe.get_doc({"doctype": "Workspace", **values}).insert(ignore_permissions=True)


def _print_format():
	_upsert("Print Format", "Pest Service Certificate", {
		"doc_type": "Pest Completion Report",
		"module": MODULE,
		"standard": "No",
		"custom_format": 1,
		"print_format_type": "Jinja",
		"disabled": 0,
		"html": CERTIFICATE_HTML,
		"css": CERTIFICATE_CSS,
	})
	make_property_setter(
		"Pest Completion Report", None, "default_print_format", "Pest Service Certificate", "Data",
		for_doctype=True, validate_fields_for_doctype=False,
	)


CERTIFICATE_CSS = """
.pc-cert { font-family: Helvetica, Arial, sans-serif; color: #1f2933; font-size: 12px; }
.pc-cert .pc-head { border-bottom: 3px solid #1d6b57; padding-bottom: 10px; margin-bottom: 14px; }
.pc-cert .pc-company { font-size: 18px; font-weight: bold; }
.pc-cert .pc-title { font-size: 22px; font-weight: bold; color: #1d6b57; text-align: center; margin: 12px 0 4px; letter-spacing: 1px; }
.pc-cert .pc-sub { text-align: center; color: #52606d; margin-bottom: 14px; }
.pc-cert table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
.pc-cert td, .pc-cert th { padding: 6px 8px; border-bottom: 1px solid #e4e7eb; vertical-align: top; text-align: left; }
.pc-cert th { background: #e6f2ee; font-weight: bold; }
.pc-cert .pc-label { width: 30%; color: #52606d; }
.pc-cert h4 { margin: 14px 0 6px; color: #1d6b57; }
.pc-cert .pc-sign td { border: none; padding-top: 40px; width: 50%; }
.pc-cert .pc-line { border-top: 1px solid #1f2933; padding-top: 4px; width: 80%; }
.pc-cert .pc-foot { margin-top: 18px; font-size: 10px; color: #52606d; text-align: center; }
"""

CERTIFICATE_HTML = """
{%- set visit = frappe.get_doc("Pest Service Visit", doc.visit) -%}
{%- set request = frappe.get_doc("Pest Service Request", visit.service_request) -%}
{%- set crew = frappe.get_all("Pest Visit Assignment", filters={"visit": doc.visit, "status": "Active"},
	fields=["staffing_role", "employee_name"], order_by="staffing_role desc") -%}
{%- set company = frappe.db.get_single_value("Global Defaults", "default_company") -%}
<div class="pc-cert">
  <div class="pc-head">
    <div class="pc-company">{{ company or "" }}</div>
    <div>Pest Control Services</div>
  </div>
  <div class="pc-title">PEST CONTROL SERVICE CERTIFICATE</div>
  <div class="pc-sub">Certificate No. {{ doc.name }}{% if doc.docstatus != 1 %} &middot; DRAFT{% endif %}</div>

  <table>
    <tr><td class="pc-label">Customer</td><td><b>{{ doc.customer }}</b></td></tr>
    <tr><td class="pc-label">Service location</td><td>{{ doc.operations_site }}</td></tr>
    <tr><td class="pc-label">Treatment for</td><td>{{ request.pest_category }}</td></tr>
    <tr><td class="pc-label">Service date</td><td>{{ frappe.utils.format_datetime(doc.actual_start, "dd MMM yyyy") }}</td></tr>
    <tr><td class="pc-label">Time on site</td><td>{{ frappe.utils.format_datetime(doc.actual_start, "HH:mm") }} &ndash; {{ frappe.utils.format_datetime(doc.actual_end, "HH:mm") }}</td></tr>
    <tr><td class="pc-label">Visit reference</td><td>{{ doc.visit }} (request {{ request.name }}{% if request.contract %}, contract {{ request.contract }}{% endif %})</td></tr>
  </table>

  <h4>Work performed</h4>
  <div>{{ (doc.work_performed or "") | replace("\\n", "<br>") }}</div>

  {% if doc.materials_used %}
  <h4>Materials applied</h4>
  <table>
    <tr><th>Item</th><th>Description</th><th style="text-align:right">Quantity</th><th>Unit</th></tr>
    {% for m in doc.materials_used %}
    <tr><td>{{ m.item_code }}</td><td>{{ m.item_name or "" }}</td><td style="text-align:right">{{ frappe.utils.flt(m.qty) }}</td><td>{{ m.uom }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}

  {% if doc.issues %}<h4>Observations</h4><div>{{ doc.issues | replace("\\n", "<br>") }}</div>{% endif %}
  {% if doc.follow_up_notes %}<h4>Recommendations / follow-up</h4><div>{{ doc.follow_up_notes | replace("\\n", "<br>") }}</div>{% endif %}

  <h4>Service team</h4>
  <table>
    {% for c in crew %}<tr><td class="pc-label">{{ c.staffing_role }}</td><td>{{ c.employee_name }}</td></tr>{% endfor %}
  </table>

  <table class="pc-sign">
    <tr>
      <td><div class="pc-line">For {{ company or "the service provider" }}</div></td>
      <td><div class="pc-line">Customer acknowledgement</div></td>
    </tr>
  </table>
  <div class="pc-foot">This certificate confirms the pest control service described above was carried out on the date shown.</div>
</div>
"""
