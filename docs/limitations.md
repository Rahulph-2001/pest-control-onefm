# Known limitations and backlog

## Gaps found against OneFM

1. **One Basic schedule per employee per day.** OneFM names Employee Schedules `{date}_{employee}_{roster_type}` and refuses a second one in `before_insert`. The plan allows back-to-back visits, but two pest visits on the same day for the same worker can't both be rostered as Basic. The allocator gives a clear error. A business decision is needed: allow `Over-Time` roster type for the second slot, or change how OneFM names schedules.
2. **Direct-SQL roster writes.** Some OneFM roster screens and mobile endpoints update `tabEmployee Schedule` with SQL, which skips document hooks. The visit start gate re-validates each linked schedule. Blocking those endpoints for pest staff is still to do.
3. **Releasing a schedule deletes it.** OneFM has no "cancelled" state for Employee Schedule, so cancelling or replacing an assignment deletes the schedule to free the roster. The history stays on the assignment (`released_employee_schedule`, reason, actor, time) and in the audit log.
4. **OneFM suspension and DSOT workflows aren't installed** on a fresh site (see [setup.md](setup.md)). Only the `workflow_state` column was added so OneFM's controller runs.
5. **Frappe is pinned to v15.117.0** because current OneFM doesn't import on newer Frappe v15 releases. Security fixes released after that version aren't included.
6. **OneFM breaks ERPNext's zero-stock valuation path** (`TypeError` from its `get_valuation_rate_` replacement). Stock posting checks availability first so users see a clear message. Other ERPNext stock flows on this stack may hit the same error.

## Out of scope for this prototype

The following are deferred:
- accounting, invoicing, payroll and purchasing
- recurring visits
- travel time
- overtime rules
- automatic reassignment after HR changes
- offline/mobile
- AI allocation
- production hardening

**Contracts / AMC:** service requests are generated from a contract on demand (an Operations Manager clicks *Generate Service Requests*). They aren't created automatically on a schedule, because the plan defers automatic recurring visits. Billing stays in OneFM Contracts and isn't touched by this app.

**Attendance sync:** if OneFM or Frappe HR refuses an Attendance (for example missing HR setup such as a holiday list), the visit still completes and the failure is recorded in the *Attendance Synced* audit event for HR to fix manually. OneFM's own `Contracts` insert also commits the transaction, so code that creates contracts must not rely on rolling them back.

**ERPNext stock posting** is implemented as an optional, manual action (Operations Manager, one Material Issue per submitted report). Returns and reversals of a posted entry are done in ERPNext directly.

Company or team scoping for Operations Managers relies on standard Frappe User Permissions. The prototype uses a single demo company.

## Not yet verified

- OneFM's Desk roster page and mobile roster APIs, which write with direct SQL. See [test-results.md](test-results.md).
- Desk UI buttons, checked manually in a browser rather than by automated tests.
