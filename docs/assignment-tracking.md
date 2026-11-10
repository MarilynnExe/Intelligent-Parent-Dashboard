# Phase 2A: Assignment tracking

Assignment completion now has its own workflow. It is separate from scored assessments and does not change CatBoost inputs, saved probabilities or the trained model. Competency tracking is the next phase-2 feature.

## Teacher workflow

1. Select an assigned class/subject and academic period in the teacher dashboard.
2. Open **Assignments & Completion**. Enter a title, instructions, assigned date and due date. Both dates must fall within the selected term/year; the deadline cannot precede the assigned date.
3. Create the assignment once for the current class. Open its **Completion register** to record each learner as Not submitted, Submitted or Excused.
4. Submitted work requires its actual submission date. If it is after the deadline, a nonblank reason is required. Submission dates cannot be in the future or before the assigned date. Reasons can also document an excuse or correction.
5. Save the register. Every entry is validated before any completion changes are written. The register reloads saved statuses and reasons.
6. Use Edit to correct the title, instructions or dates. Class, subject and academic period stay fixed; withdraw/recreate incorrectly targeted work. Deadline edits that would create late submissions without reasons are rejected until those records have reasons.
7. Withdraw hides work from normal lists, rates and missing-work guidance while preserving its records and correction history. Enable **Show withdrawn** to inspect or restore it.

Only teachers currently assigned to that class and subject can manage its work. Another teacher assigned to the same class/subject can continue the workflow if responsibilities change. Archived or transferred recipients are read-only; their existing records remain in history.

## Parent workflow and status meanings

Choose a linked learner and academic period, then open **Assignments**. The visible page refreshes every 30 seconds; **Refresh progress** updates it immediately. Assignment tracking and guidance remain available when there are no assessment records or predictive results.

| Status | Meaning |
|---|---|
| Pending | Not submitted, but the due date has not passed |
| Missing | Not submitted and the current date is after the due date |
| Submitted on time | Recorded submission date is on or before the deadline |
| Submitted late | Recorded submission date is after the deadline; the reason is shown |
| Excused | Teacher recorded an exemption; excluded from the rate |

Dates use **Africa/Nairobi**. Work stays pending throughout its due date and becomes missing on the following calendar day. Missing/late status is derived when records are read; there is no background job changing statuses at midnight. Reads never send notifications or write completion records.

The completion rate is submitted work divided by non-excused work due on or before today. Both on-time and late submissions count as completed. Future deadlines and withdrawn work do not enter the rate. With no eligible due work, the dashboard shows **No assignments due**, rather than 0%.

## Joining, transferring and restoration

Newly enrolled learners automatically receive existing active class assignments whose deadlines have not passed. The same synchronization runs on class changes and learner restoration. Learners do not inherit already-overdue work from before joining. Rejoining reuses existing completion records without resetting them.

Existing recipients remain linked to earlier assignments for history after a transfer. Parents continue to see those earlier assignment records for linked, unarchived learners. Teachers cannot change a recipient's completion once that learner is archived or has left the assignment's class.

## Guidance and notifications

Missing work produces a single aggregated expert-system recommendation listing up to three tasks, with a count of any additional tasks. This guidance is computed independently from academic-model recommendations and requires no CatBoost prediction or assessment record.

Teacher saves check aggregated follow-up alerts for linked parents. Alerts use the existing Academic Performance notification preference, concise/detailed style, active-account checks and deduplication. Repeated saves update an unread matching alert instead of adding duplicates. When missing work is resolved, an existing unread alert is updated to reflect that resolution without adding another alert.

Deadline passage alone changes dashboard status/guidance but does not send a notification. Scheduled reminders remain deferred. **Retry follow-up alerts** retries delivery if a notification service error occurs; the assignment/completion save is retained even if delivery fails.

## Interfaces and storage

New additive tables: `class_assignments` and `assignment_completions`, with a unique assignment/learner relationship. Startup creates them without altering existing source tables. Assignment metadata and completion corrections use the existing protected `record_changes` history.

- `GET/POST /api/teacher/class-assignments`: list by class, subject and period, or create class work.
- `PUT/DELETE /api/teacher/class-assignments/{id}`: edit details or withdraw.
- `PATCH /api/teacher/class-assignments/{id}/status`: restore/withdraw using `is_withdrawn`.
- `GET /api/teacher/class-assignments/{id}/register`: recipient statuses, derived display statuses and editability.
- `PUT /api/teacher/class-assignments/{id}/completions`: bulk-save entries with `student_id`, `status`, `submitted_on` and `reason`.
- `POST /api/teacher/class-assignments/{id}/notify`: retry/check follow-up delivery.
- `GET /api/parent/children/{id}/assignments?term=Term%203&academic_year=2026`: linked-parent summary, counts, rate and guidance. `include_withdrawn=true` includes withdrawn records for history without counting them.

Existing teaching assignments remain at `/api/teacher/assignments`; they are class/subject permissions, not learner work. Existing scored assessments labelled “Assignment” are not automatically converted, since scores do not establish submission status or deadlines.

## Demo and verification

From `backend/` with the project environment active:

```bash
python -m scripts.seed_demo --term 'Term 3' --year 2026 --with-assignments
python -m pytest tests -q
```

The explicit flag adds three fictional examples covering missing, late, excused and upcoming work. Matching examples and their completion corrections are preserved on repeat runs. Use the current academic period for a live upcoming/overdue demonstration. Examples in other periods retain their real date-based interpretation.

Assignment tests also support the existing disposable `CRUD_TEST_DATABASE_URL` ending in `_crud_test`; its tables are created/dropped by the fixture. Browser rehearsal writes fictional assignments to a separately seeded demo server:

```bash
python -m scripts.browser_assignments --base-url http://127.0.0.1:18082
```

The browser rehearsal checks create/edit/withdraw/restore, automatic missing status, late reasons, completion saving, actual parent polling and desktop/mobile layout. It requires a day after the first day of term to create a valid within-term overdue example. Screenshots default to `/tmp/ipd-assignment-screenshots`.
