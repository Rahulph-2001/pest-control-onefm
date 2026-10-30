HR_VERIFIER = "Pest HR Verifier"
OPERATIONS_MANAGER = "Pest Operations Manager"
FIELD_USER = "Pest Field User"

PEST_ROLES = (HR_VERIFIER, OPERATIONS_MANAGER, FIELD_USER)

TECHNICIAN = "Technician"
SUPERVISOR = "Supervisor"

# CRM documents a service request may originate from. Only those installed on the
# site are accepted (ERPNext Lead/Opportunity, Frappe CRM CRM Lead/CRM Deal).
CRM_SOURCE_DOCTYPES = ("Lead", "Opportunity", "CRM Lead", "CRM Deal")

ASSIGNMENT_DOCTYPE = "Pest Visit Assignment"

# Employee Schedule availabilities that make an employee unavailable for the whole day.
NON_WORKING_AVAILABILITY = (
	"Day Off",
	"Client Day Off",
	"Sick Leave",
	"Annual Leave",
	"Emergency Leave",
	"Suspended",
)
