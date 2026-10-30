# Design: reuse mapping, rules and controls

OneFM reference: `ONE-F-M/one_fm` branch `version-15`. Schemas were inspected at commit `e15a521871b8b4e62f0bde7b374bb7b8fc89d52f` (30 Oct 2026). The commits actually installed are listed in [`stack-lock.txt`](stack-lock.txt).

## 1. Reuse mapping

| Need | Record used | Notes |
|---|---|---|
| Customer enquiry | ERPNext **Lead / Opportunity** or Frappe CRM **CRM Lead / CRM Deal** | The request stores `crm_reference_doctype` + `crm_reference_name`. The link is manual; there is no automatic sync. |
| Customer | ERPNext **Customer** | |
| Service location | OneFM **Operations Site** | Custom fields `pest_customer` and `pest_control_notes`. No second site master. |
| Shift / post | OneFM **Operations Shift**, **Operations Role** | The visit picks a shift of the request's site. Roles are optional per staffing slot. |
| Roster (authoritative) | OneFM **Employee Schedule** | One per active assignment, with `reference_doctype = Pest Visit Assignment` and `reference_docname = <assignment>`. `start_datetime` / `end_datetime` are set to the visit's window. |
| Employee | Frappe HR **Employee** | `status`, `relieving_date`, `user_id` (field-account mapping) |
| Working period | Frappe HR **Shift Assignment** + **Shift Type** | Must be submitted and Active, and its window must cover the visit |
| Leave | Frappe HR **Leave Application** | Submitted + Approved, any leave type |
| Materials | ERPNext **Item**, **UOM** | Child table `Pest Material Item` |

### New DocTypes (app `pest_control`)

| DocType | Purpose |
|---|---|
| Pest Service Request | customer, OneFM site, CRM source, pest category, description, requested date, status |
| Pest Service Visit | request, OneFM shift, scheduled window, technician/supervisor counts, OneFM roles, required qualification, status, planned materials |
| Pest Visit Assignment | visit + staffing role → OneFM Employee Schedule. Holds only replacement and cancellation history; times always come from the schedule and visit. |
| Pest Completion Report | submittable; actual times, work performed, issues, follow-up, materials used |
| Pest Employee Verification | one per employee; private evidence, verifier checklist, role authorization, decision |
| Pest Employee Qualification | qualification type, certificate, validity, private evidence, decision |
| Pest Qualification Type | master list of qualifications |
| Pest Audit Event | append-only event log |

## 2. Allocation rules

An employee can be assigned only if **all** of the following hold. Every rule fails closed: missing data means "not eligible".

1. Employee `status = Active` and not relieved before the visit ends.
2. Pest Employee Verification is **Verified** and authorizes the staffing role (Technician or Supervisor).
3. If the visit requires a qualification: a **Verified** Pest Employee Qualification of that type, valid from on or before the visit start and valid until on or after the visit end.
4. An active, submitted Shift Assignment whose Shift Type window covers the whole visit. Overnight shifts are handled.
5. No submitted, approved Leave Application overlapping the visit dates.
6. No conflicting OneFM Employee Schedule of **any** kind:
   - Working schedules overlap when `existing.start < new.end and new.start < existing.end`. Back-to-back schedules are allowed.
   - A Working schedule without times on the visit date counts as a conflict, because availability can't be confirmed.
   - Day Off, Client Day Off, Sick/Annual/Emergency Leave or Suspended on the visit date counts as a conflict.
7. The employee isn't already active on the same visit in another role.
8. The role's slots aren't already full.

The Ops Manager sees the result of these checks (`pest_control.eligibility.check_eligibility`) without seeing HR evidence.

### Concurrency and integrity

Every action runs in one transaction under a savepoint (`utils.atomic`):

1. Lock the visit row (`SELECT … FOR UPDATE`).
2. Lock each affected Employee row, in sorted order to avoid deadlocks.
3. Run the conflict query as a **locking read**, so it sees schedules committed by a competing transaction that held the employee lock first.
4. Write the visit, assignment, OneFM schedule and audit event, or roll all of them back.

| Action | Behaviour |
|---|---|
| Allocate | Creates the assignment, then its Employee Schedule |
| Cancel assignment | Marks it Cancelled with reason, actor and time. Releases (deletes) the OneFM schedule, keeping its name in `released_employee_schedule`. |
| Replace | Ends the old assignment as Replaced, then allocates the new worker. If the new worker is ineligible, nothing changes. |
| Reschedule | Re-checks every assigned worker against the new window, then moves the visit and recreates each schedule. A repeated identical request is a no-op. Any failure keeps the original schedule. |
| Start | Requires status Scheduled, full coverage, fresh eligibility for every worker, and each OneFM schedule still matching the visit (employee, Working, times, back-reference) |
| Complete | Submitting the completion report moves the visit from In Progress to Completed. Only one submitted report is allowed per visit. |

### Native OneFM paths

Hooks on **Employee Schedule** (`onefm_integration.py`) run after OneFM's own controller:

- Pest-linked schedules can't be created, edited or deleted except by the allocation service.
- Any other schedule that would overlap pest work (or mark a day off on a pest-work day) is rejected.

OneFM's Desk roster page and mobile APIs write some changes with **direct SQL**, which bypasses document hooks. The start gate's roster re-check catches those changes before work starts. Restricting those routes for pest staff is listed as a gap.

## 3. Verification workflow

States: **Pending, Verified, Rejected, Revoked**.

| Decision | From |
|---|---|
| Verified | Pending, Rejected, Revoked (after re-review) |
| Rejected | Pending (reason required) |
| Revoked | Verified (reason required) |

- Only **Pest HR Verifier** or System Manager may decide (`verification.decide`).
- **No self-approval:** refused if the target employee's `user_id` is the reviewer, or the reviewer's own Employee is the target.
- **Verified** requires every checklist item to be ticked and evidence attached. Uploading a file alone is not enough.
- Evidence must be a **private** file.
- Any change to evidence, checklist or authorization on a Verified or Rejected record returns it to **Pending** and logs `Verification Invalidated`.
- Decision fields (`verification_status`, `reviewed_by`, `decision_time`, `decision_reason`) are guarded. Forms, `frappe.client.set_value` and REST updates that change them are refused.

Evidence checklist for this prototype, with fictional data only:
- identity document type and number, plus a scan
- an employment record
- right-to-work proof
- the verifier confirms each item

The business owner must define the real checklist for each country and service.

## 4. Roles and record access

| Role | Can | Cannot |
|---|---|---|
| Pest HR Verifier | read/write verification and qualification records and their evidence; decide | decide on own record; allocate staff |
| Pest Operations Manager | create requests and visits; allocate, replace, cancel, reschedule, start; see eligibility results and operations audit events | read verification records or evidence files; see verification audit events |
| Pest Field User | read visits and assignments they're actively assigned to; create and submit the completion report for those visits; start an assigned visit | see other visits; verify or allocate; edit the audit log |

Enforcement:
- `permission_query_conditions` restricts list views and `get_list`.
- `has_permission` restricts direct links and API reads.
- Private files follow the permission of the document they're attached to.
- Guarded status fields are server-side.
- Assignments can only be written by the service.

## 5. Audit

- **Pest Audit Event** records: event type, category (Verification / Operations), reference, actor, time, reason, and JSON details.
- It can only be inserted by the system. Updates and deletes are refused in the controller, including for Administrator.
- Field users have no role permission on it. Ops Managers only see the Operations category.
- Every DocType also has `track_changes` (Frappe Version history).

Events logged:
- verification decisions and invalidations
- assignment created, cancelled or replaced
- visit status changes and reschedules
- Employee status changes
