# Setup notes

## Requirements

- Docker Desktop with at least ~25 GB free on the drive holding its disk image. Low disk space caused I/O errors and a corrupted image during this build.
- About 8 GB of RAM for Docker.

## Steps

```bash
docker compose -f docker/docker-compose.yml up -d
# Git Bash on Windows: export MSYS_NO_PATHCONV=1 first
docker compose -f docker/docker-compose.yml exec frappe bash /workspace/pest_control/docker/setup-bench.sh
```

Then complete the ERPNext setup wizard. You can do this in the browser at http://localhost:8000 (log in as Administrator / admin), or headless:

```bash
bench --site pest.localhost execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
  --kwargs '{"args": {"language":"English","country":"India","timezone":"Asia/Kolkata","currency":"INR",
  "full_name":"Demo Admin","email":"admin@example.com","password":"admin","company_name":"PestCare Demo",
  "company_abbr":"PCD","chart_of_accounts":"Standard","fy_start_date":"2026-04-01","fy_end_date":"2027-03-31"}}'
```

Demo data and journey:

```bash
bench --site pest.localhost execute pest_control.demo.run_journey
```

Demo users all have the password `Demo@12345`:

| User | Role |
|---|---|
| `ops_pc@example.com` | Pest Operations Manager |
| `hr_pc@example.com` | Pest HR Verifier |
| `field_pc@example.com` | Pest Field User, mapped to employee Arun |

## Setup blockers found and how they were handled

These are problems with installing **OneFM `version-15`** on a fresh site. They are not problems in the pest_control app.

| # | Problem | Handling |
|---|---|---|
| 1 | OneFM imports `get_email_template` from Frappe's `workflow_action`, which Frappe removed after **v15.117.0** (commit `99a7c51a`, 5 Aug 2026). With the latest Frappe v15, OneFM fails to import. | Pinned **Frappe v15.117.0**. Helpdesk is pinned to **v1.30.2**, the last release that accepts it. |
| 2 | OneFM needs Frappe **`lending`**. Its README doesn't list it, but its CI installs it. | Added to `docker/apps.txt`. Lending's own post-install patch fails on first install, so `migrate` is run and then `lending.install.after_install` is rerun. |
| 3 | OneFM's installer creates custom fields per DocType and skips **every** field on a DocType when one conflicts. Frappe HR now ships `Employee.iban` as standard, so all OneFM Employee fields were skipped, including `project`, which OneFM code depends on. | `pest_control.setup.onefm_repair.repair_custom_fields` re-applies fields one at a time (121 + 5 created) and skips only real conflicts. |
| 4 | OneFM code reads `Employee.one_fm_fourth_name_in_arabic`, but its field list creates `one_fm_forth_name_in_arabic`. Every Employee save fails. | The repair step adds the correctly spelled field. |
| 5 | OneFM's Employee Schedule workflow fails to install (missing workflow states), so `workflow_state` never exists. The Employee Schedule controller reads it on every update. | The repair step adds the column. The suspension and DSOT workflows themselves are **not** installed. |
| 6 | OneFM's `Employee.on_update` calls `frappe.db.commit()` (push notification). | Tests create employees only in `setUpClass`. Be aware of this in any code that saves an Employee inside a larger transaction. |
| 7 | OneFM makes `Department.department_code` mandatory, so the setup wizard's default departments fail. | Harmless. The setup wizard still completes. |
| 8 | Helpdesk front-end build error (Vite plugin) during `bench build`. | Not needed for this prototype. The Helpdesk UI may not load. |
| 9 | Skipped OneFM fields: `HD Ticket` fields that link to `Process` (OneFM's `one_bpmn` app, not installed), plus `Notification Log.title` (now standard). | Not needed. |

Environment notes:
- The `frappe/bench` image's default Python is 3.14, which is too new for Frappe v15, so bench runs from a Python 3.12 virtualenv.
- The MariaDB 11 client requires TLS by default, so `~/.my.cnf` sets `skip-ssl` for the local dev server.

## Account setup rule

Frappe HR creates a *User Permission* that restricts a linked user to their own Employee record. For **HR Verifier** accounts that are also employees, untick **Create User Permission** on their Employee, or they can't open other employees' verification records.
