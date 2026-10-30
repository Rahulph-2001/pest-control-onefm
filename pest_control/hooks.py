app_name = "pest_control"
app_title = "Pest Control"
app_publisher = "Rahul P H"
app_description = "Pest control operations and verified manpower allocation on OneFM"
app_email = "rahulph719@gmail.com"
app_license = "mit"

required_apps = ["frappe", "erpnext", "hrms", "one_fm"]

after_install = "pest_control.setup.install.after_install"
after_migrate = "pest_control.setup.install.after_migrate"

app_include_js = "/assets/pest_control/js/verification_actions.js"

# OneFM's Employee Schedule is the authoritative roster. These hooks run after
# OneFM's own controller methods.
doc_events = {
	"Employee Schedule": {
		"validate": "pest_control.onefm_integration.employee_schedule_validate",
		"on_trash": "pest_control.onefm_integration.employee_schedule_on_trash",
	},
	"Employee": {
		"on_update": "pest_control.audit.employee_on_update",
	},
}

permission_query_conditions = {
	"Pest Service Visit": "pest_control.permissions.visit_query",
	"Pest Visit Assignment": "pest_control.permissions.assignment_query",
	"Pest Completion Report": "pest_control.permissions.completion_report_query",
	"Pest Audit Event": "pest_control.permissions.audit_event_query",
}

has_permission = {
	"Pest Service Visit": "pest_control.permissions.visit_has_permission",
	"Pest Visit Assignment": "pest_control.permissions.assignment_has_permission",
	"Pest Completion Report": "pest_control.permissions.completion_report_has_permission",
	"Pest Audit Event": "pest_control.permissions.audit_event_has_permission",
}
