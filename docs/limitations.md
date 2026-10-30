# Known limitations and backlog

## Gaps found against OneFM

1. **One Basic schedule per employee per day.** OneFM names Employee Schedules `{date}_{employee}_{roster_type}` and refuses a second one in `before_insert`. The plan allows back-to-back visits, but two pest visits on the same day for the same worker can't both be rostered as Basic. The allocator gives a clear error. A business decision is needed: allow `Over-Time` roster type for the second slot, or change how OneFM names schedules.
2. **Direct-SQL roster writes.** Some OneFM roster screens and mobile endpoints update `tabEmployee Schedule` with SQL, which skips document hooks. The visit start gate re-validates each linked schedule. Blocking those endpoints for pest staff is still to do.
3. **Releasing a schedule deletes it.** OneFM has no "cancelled" state for Employee Schedule, so cancelling or replacing an assignment deletes the schedule to free the roster. The history stays on the assignment (`released_employee_schedule`, reason, actor, time) and in the audit log.

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

**ERPNext stock posting:** material rows link to Items with quantity and unit, but no Stock Entry is posted yet.

Company or team scoping for Operations Managers relies on standard Frappe User Permissions. The prototype uses a single demo company.

4. **OneFM suspension and DSOT workflows aren't installed** on a fresh site (see [setup.md](setup.md)). Only the `workflow_state` column was added so OneFM's controller runs.
5. **Frappe is pinned to v15.117.0** because current OneFM doesn't import on newer Frappe v15 releases. Security fixes released after that version aren't included.

## Not yet verified

- The concurrency guarantee (competing allocations can't both succeed) is designed with row locks and locking reads. The automated tests check it sequentially. A two-connection test is still to be written.
- HTTP-level REST calls and OneFM's Desk roster page haven't been tested. See [test-results.md](test-results.md).
