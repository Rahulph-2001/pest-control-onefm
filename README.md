# pest-control-onefm

Pest Control Management prototype on **OneFM**, Frappe, ERPNext, Frappe HR and CRM (v15): service visits, verified manpower allocation and audit controls.

> **Status: working prototype.** It runs on an installed OneFM stack (Frappe v15.117.0, ERPNext, Frappe HR, CRM, OneFM `version-15`), and **all 11 mandatory acceptance cases pass**. Concurrent allocations are refused under real parallel load, 18/18 HTTP access checks pass, ERPNext stock posting works (3/3 tests), and contracts/AMC, the service certificate, the dashboard, the daily manpower report and attendance sync are tested (8/8). The enquiry → visit → OneFM allocation → completion report journey runs end to end. See [docs/test-results.md](docs/test-results.md).

## What it does

A CRM enquiry becomes a **Pest Service Request** for a customer's OneFM site, which is scheduled as a **Pest Service Visit**. A verified crew is then allocated through **OneFM Employee Schedule**, and the visit is closed with a **Pest Completion Report**.

| Area | Approach |
|---|---|
| Sites | Reuses OneFM **Operations Site** (adds a Pest Control Customer field), with no second site master |
| Roster | Each assignment creates exactly one OneFM **Employee Schedule**, linked via its `reference_doctype` / `reference_docname`. The schedule is the authoritative record. |
| CRM | Requests link to an existing Lead / Opportunity / CRM Lead / CRM Deal |
| Materials | Child table of ERPNext **Item**, quantity and unit (validated against the Item's UOMs). Optional posting as an ERPNext **Stock Entry (Material Issue)**, once per report |
| Contracts / AMC | Extends OneFM **Contracts** with a contract type (AMC, One-Time, Seasonal) and a services table (site, pest, frequency). *Generate Service Requests* creates the requests for the contract period; repeating it creates nothing new. |
| Attendance | Completing a visit marks each crew member **Present** in Frappe HR **Attendance**, using the report's actual times and linked to the assignment. Existing attendance is left alone. |
| Service certificate | *Pest Service Certificate* print format (default) on the completion report |
| Dashboard | **Pest Control** workspace: number cards (visits today, scheduled, in progress, understaffed, pending verifications, active contracts), charts and shortcuts |
| Daily manpower report | *Daily Manpower Deployment*: who is deployed where on a date, including **unfilled** positions |

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

App versions and install order are listed in `docker/apps.txt`. The exact commits are in [docs/stack-lock.txt](docs/stack-lock.txt).

See [docs/setup.md](docs/setup.md) for the full setup steps, demo users, and the **OneFM install problems found on a fresh site and how each was handled**.

## Docs

- [docs/design.md](docs/design.md): reuse mapping, allocation rules, verification workflow, roles, audit
- [docs/test-results.md](docs/test-results.md): acceptance results and what isn't covered
- [docs/setup.md](docs/setup.md): setup, demo data, OneFM install findings
- [docs/limitations.md](docs/limitations.md): known gaps and backlog

## Known gaps

- OneFM allows **one Basic Employee Schedule per employee per day**, so two back-to-back pest visits on the same day can't both be rostered. This needs a business decision.
- OneFM's Desk roster page writes some changes with direct SQL, which bypasses document hooks. The visit start gate re-checks the roster to catch this.
- Frappe is pinned to v15.117.0 because current OneFM doesn't import on newer v15 releases. See [docs/setup.md](docs/setup.md).

## License

MIT
