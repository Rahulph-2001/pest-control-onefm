# pest-control-onefm

Pest Control Management prototype on **OneFM**, Frappe, ERPNext, Frappe HR and CRM (v15): service visits, verified manpower allocation and audit controls.

> **Status: in progress.** The extension app is written but has not yet been run against an installed OneFM stack. Test results will be recorded in `docs/` once the stack is up.

## What it does

A CRM enquiry becomes a **Pest Service Request** for a customer's OneFM site, which is scheduled as a **Pest Service Visit**. A verified crew is then allocated through **OneFM Employee Schedule**, and the visit is closed with a **Pest Completion Report**.

| Area | Approach |
|---|---|
| Sites | Reuses OneFM **Operations Site** (adds a Pest Control Customer field), with no second site master |
| Roster | Each assignment creates exactly one OneFM **Employee Schedule**, linked via its `reference_doctype` / `reference_docname`. The schedule is the authoritative record. |
| CRM | Requests link to an existing Lead / Opportunity / CRM Lead / CRM Deal |
| Materials | Child table of ERPNext **Item**, quantity and unit (validated against the Item's UOMs) |

## Controls

- **Employee verification:** Pending, Verified, Rejected or Revoked, decided by a *Pest HR Verifier*. Self-approval is blocked, evidence files must be private, and any material change returns the record to Pending.
- **Eligibility, fail-closed:** active employment, Verified status, authorization for the staffing role, a verified qualification valid through the visit end, an active HR Shift Assignment covering the visit, no approved leave, and no conflicting OneFM schedule (any work, not only pest control).
- **Overlap rule:** `existing.start < new.end and new.start < existing.end`. Back-to-back visits are allowed.
- **Concurrency:** visit and employee row locks plus locking reads, all inside one transaction or savepoint.
- **Start gate:** full coverage, fresh eligibility, and a check that each OneFM schedule still matches the visit.
- **Native OneFM guard:** a `doc_events` hook blocks edits to pest-linked schedules outside the service and rejects native schedules that clash with pest work.
- **Guarded fields:** status and decision fields can't be set through forms or the API.
- **Audit:** an immutable **Pest Audit Event** log plus document versions.
- **Roles:** *Pest HR Verifier*, *Pest Operations Manager* and *Pest Field User*. Field users only see visits they are assigned to.

## Layout

```
pest_control/            Frappe app (bench get-app this repo)
  allocation.py          allocate / replace / cancel / reschedule / start / cancel visit
  eligibility.py         verification, qualification, availability, leave, overlap checks
  onefm_integration.py   Employee Schedule hooks
  verification.py        HR decision workflow
  permissions.py         record-level access
docker/                  isolated dev stack (Frappe v15 + ERPNext + HR + CRM + OneFM)
```

## Development setup

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml exec frappe bash /workspace/pest_control/docker/setup-bench.sh
```

App versions and install order are listed in `docker/apps.txt`. The exact commits are written to `docs/stack-lock.txt` after setup.

## Known gaps

- OneFM allows **one Basic Employee Schedule per employee per day**, so two back-to-back pest visits on the same day can't both be rostered. This needs a business decision.
- OneFM's Desk roster page writes some changes with direct SQL, which bypasses document hooks. The visit start gate re-checks the roster to catch this.
- Stock posting (Stock Entry for consumption) is not implemented yet; only Item links are.

## License

MIT
