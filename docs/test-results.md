# Test results

**Run:** 31 Oct 2026, site `pest.localhost`, using the stack in [`stack-lock.txt`](stack-lock.txt): Frappe v15.117.0, ERPNext v15.124.3, HRMS v15.64.7, CRM v1.90.0, OneFM `version-15` @ `e15a5218`.

```
bench --site pest.localhost run-tests --skip-test-records --skip-before-tests \
      --module pest_control.tests.test_acceptance
Ran 11 tests in 10.6s
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

## Not covered by automated tests

| Check | Status |
|---|---|
| Two genuinely concurrent allocations (two DB connections) | **Not run.** The locking design is in place, but only the sequential path is tested. |
| HTTP REST calls (`/api/resource`, `/api/method`) | Not run over HTTP. The tests call the same server functions (`frappe.client.set_value`, whitelisted methods) in-process. |
| OneFM Desk roster page and mobile APIs (direct SQL writes) | Not tested. These bypass document hooks; the start gate re-check is the mitigation. |
| Desk UI buttons (Allocate, Reschedule, Start, Verify) | Manual check only |
| Stock posting (Stock Entry) | Not implemented (optional scope) |
