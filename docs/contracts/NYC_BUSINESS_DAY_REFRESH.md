# Official refresh clock

City sources update on **NYC business days**, usually between 5pm and 7pm Eastern. Saturday 2026-09-05 showing Friday’s `official_daily_machine_report` is expected.

## Schedule

| Job | When |
|---|---|
| Discovery Feed Refresh | 7:00pm America/New_York, Monday–Friday |
| Skip | Saturday, Sunday, NYC public holidays |
| Catch-up | After a successful Discovery run on a business day |
| Manual `workflow_dispatch` | Allowed any day |

Catch-up has no independent clock. If Discovery does not run, catch-up does not invent a Saturday pull.

## Product effect

The phone keeps Friday’s official rows through the weekend. Catch-up still does not expire rows.

Street-corridor (`CORRIDOR_READY`) work is separate from this clock.
