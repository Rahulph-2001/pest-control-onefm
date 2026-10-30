# Test results

**Run:** 31 Oct 2026, site `pest.localhost`, using the stack in [`stack-lock.txt`](stack-lock.txt): Frappe v15.117.0, ERPNext v15.124.3, HRMS v15.64.7, CRM v1.90.0, OneFM `version-15` @ `e15a5218`.

```
bench --site pest.localhost run-tests --skip-test-records --skip-before-tests \
      --module pest_control.tests.test_acceptance
Ran 11 tests in 8.4s
OK
```

The suite was run twice in a row, and both runs passed. The flags skip *other* apps' global test fixtures; Helpdesk's `before_tests` hook fails on this site's email configuration.

## Mandatory cases (plan page 6)

| # | Case | Test | Result |
|---|---|---|---|
| 1 | CRM enquiry links to a service request for the right customer and site | `test_01` | ✅ Pass |
| 2 | OneFM installed; visit with valid times, counts and OneFM site | `test_02` | ✅ Pass |
| 3 | Allocation creates matching OneFM Employee Schedule; visit coverage matches roster | `test_03` | ✅ Pass |
| 4 | Reject Pending, Rejected or Revoked verification, inactive employment, wrong role, missing or expired qualification, approved leave, no working period, outside working hours | `test_04` | ✅ Pass |
| 5 | Reject overlaps: second pest visit, native OneFM schedule clashing with pest work, existing non-pest OneFM work, OneFM Day Off | `test_05` | ✅ Pass |
| 6 | Reschedule moves the OneFM schedule; retry is a no-op; a failed reschedule keeps the original | `test_06` | ✅ Pass |
| 7 | Replace a worker: history and reason kept, schedule released, counts correct, one person can't fill two roles; ineligible replacement changes nothing | `test_07` | ✅ Pass |
| 8 | Understaffed start blocked; staffed visit started and completed by the field user's report with materials | `test_08` | ✅ Pass |
| 9 | Invalid quantity and unit rejected; field user can't allocate; API writes to guarded fields refused; direct assignment insert refused; self-approval refused; native edit or delete of pest-linked schedule refused | `test_09` | ✅ Pass |
| 10 | Revocation after assignment blocks start; re-verification restores it; decisions keep actor, time and reason; evidence change returns to Pending | `test_10` | ✅ Pass |
| 11 | Field user sees only own visits; HR evidence and verification records closed to field and ops users; audit events can't be deleted | `test_11` | ✅ Pass |

## End-to-end journey

`bench --site pest.localhost execute pest_control.demo.run_journey`:

```
CRM Lead CRM-LEAD-2026-00001
 → Pest Service Request PSR-2026-00021
 → Pest Service Visit PSV-2026-00022 (Draft → Scheduled)
 → technician PVA-00023 → OneFM Employee Schedule 2026-10-30_HR-EMP-00001_Basic 09:00–11:00
 → supervisor PVA-00024 → OneFM Employee Schedule 2026-10-30_HR-EMP-00002_Basic 09:00–11:00
 → unverified worker refused
 → rescheduled, started (In Progress)
 → Pest Completion Report PCR-2026-00025 submitted by the field user → visit Completed
```

## Concurrent allocation (case 5, "competing requests")

`bench --site pest.localhost execute pest_control.tests.concurrency_check.run`

Two threads, each with its own database connection, allocate the same technician to two overlapping visits at the same moment. Each keeps its transaction open for 1.5 s before committing.

```
PSV-2026-00029  ok    PVA-00030                                     2.75 s
PSV-2026-00028  refused "Overlaps OneFM schedule 2026-11-30_HR-EMP-00017_Basic"  2.75 s (waited on lock)
active OneFM schedules created: 1   →  passed: true
```

The losing request blocked on the Employee row lock until the winner committed. Its locking read then saw the committed schedule, and it was refused. The check cancels both visits afterwards.

## HTTP / REST checks (cases 9 and 11 over the wire)

`node scripts/http_checks.mjs http://localhost:8000` runs against `bench serve`, logging in as each demo user. **18/18 passed:**

| User | Allowed | Refused (HTTP 403) |
|---|---|---|
| Operations Manager | list visits | set visit `status`; insert Pest Visit Assignment; read verification record; download private evidence; `verification.decide`; delete audit event |
| HR Verifier | read verification; download evidence | set `verification_status`; `allocation.allocate` |
| Field User | list shows only own visit | open another visit by direct link; read verification; download another employee's evidence; allocate; decide; read audit log |

## Optional stock transaction

`run-tests --module pest_control.tests.test_stock_posting`: **3/3 passed.**

| Check | Result |
|---|---|
| Submitted report posts one ERPNext **Stock Entry (Material Issue)**; stock drops by the used quantity; the entry is linked on the report | ✅ |
| A second posting for the same report is refused; stock unchanged | ✅ |
| Insufficient stock is refused; no entry is created and stock is unchanged | ✅ |
| Field user cannot post | ✅ |

With OneFM installed, ERPNext's own zero-stock path raises a `TypeError`, because OneFM replaces `get_valuation_rate_` with an incompatible signature. The app therefore checks availability itself first, under a row lock on Bin, and gives a clear message.

## Contracts, attendance, report, certificate, dashboard

`run-tests --module pest_control.tests.test_extras`: **8/8 passed.**

| Check | Result |
|---|---|
| An AMC contract (OneFM Contracts) with monthly cockroach and quarterly termite services over Nov 2026 to Jan 2027 generates **4** Open requests (3 + 1) on the right dates | ✅ |
| Generating again creates 0 and skips 4 (idempotent) | ✅ |
| A contract request for the wrong customer, or a request with no CRM source and no contract, is refused | ✅ |
| A field user can't generate contract requests | ✅ |
| Completing a visit marks the technician and supervisor **Present** (2 h, linked to the assignment) and logs *Attendance Synced* | ✅ |
| Existing attendance for that day is left untouched | ✅ |
| The Daily Manpower Deployment report lists the assigned technician with their OneFM schedule, plus an **Unfilled** supervisor row; the fully-staffed flag flips when the supervisor is added | ✅ |
| The Pest Service Certificate renders with title, customer, report number and crew, and is the default print format | ✅ |
| The workspace, number cards, chart and report exist | ✅ |

Demo journey on the live site: the completed visit marked both crew members Present for 28 Oct 2026 (1.75 h).

## Not covered by automated tests

| Check | Status |
|---|---|
| OneFM Desk roster page and mobile APIs (direct SQL writes) | Not tested. These bypass document hooks; the visit start gate re-check is the mitigation. |
| Desk UI buttons (Allocate, Reschedule, Start, Verify, Post Material Consumption) | Manual browser check |
