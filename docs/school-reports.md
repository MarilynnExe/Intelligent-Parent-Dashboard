# Phase 2D — administrator school-wide reporting

Open **School Reports** in the administrator dashboard. Select a year, term and optional grade/stream, then generate the report. Filter changes reload it; generate again after teacher records change. This is a read-only view of one configured school's database, not a multi-school tenancy feature.

## Reports available

- Active learner population, academic assessment coverage and mean.
- Grade and class summaries with assessment, attendance, assignment, competency and analytics coverage.
- Subject means for subjects with recorded assessments, with learner and record counts.
- Recorded monthly attendance counts and rates.
- Analytics freshness counts and advisory support-status totals from current valid snapshots only.
- Previous-term comparison, including Term 1 to the previous year's Term 3, with coverage context and percentage-point changes.
- A paginated learner follow-up register: all active learners, analytics needing calculation, no assessments, missing work, or unassessed competency slots.
- CSV exports of school summary, grade summaries, class summaries, subjects, attendance trend and all matching learner rows.

The learner follow-up selector affects only that table and its CSV. It does not alter school/class totals. Main grade/stream and period filters apply to every dataset. An empty stream means No stream; omitting the stream filter means All streams. Null and blank stream values share the No stream group. Learner pages contain 50 rows in the UI, with previous/next controls; API limits may be 1–200. Learner CSV downloads include every matching learner, not just the current page.

## Definitions that matter

**Population:** current active learner enrollment, even for earlier years/terms. Archived learners and their records are excluded. Class transfers group retained records under the learner's current class. Historical enrollment is not yet versioned. The report captures the selected population before fetching its source data in batches.

**Academic mean:** first average each learner's recorded assessment percentages in the selected period; then give each assessed learner equal weight in the school, grade or class mean. Subject means similarly give each assessed learner equal weight within that subject. Unassessed learners are counted explicitly and never assigned a zero. Unequal assessment difficulty, curriculum and coverage limit comparisons across groups. Academic coverage is assessed learners / current active learners; subject rows do not claim an expected curriculum or subject-enrollment denominator.

**Attendance:** counts the selected term's recorded learner-days. Rate is `(Present + Late) / (Present + Late + Absent)`. Excused days are reported separately and excluded from this denominator; unrecorded days are neither Present nor Absent. There is no inferred school-day attendance coverage, official holiday calendar or enrollment-days denominator. Months with no recorded entries are omitted. Term windows retain the existing January–April, May–August and September–December prototype buckets.

**Assignments:** counts existing recipient records of non-withdrawn assignments in the period. It does not create recipients on read. Completion is submitted recipient records / recipient records due by the report's Africa/Nairobi date, excluding Excused and withdrawn work. Both on-time and late submissions count as complete. Future work is Pending; unsubmitted work becomes Missing after its due date. An overdue task with no recipient record is not silently assigned retrospectively. Retained previous-class work follows its active recipient's current class for reporting. Counts are learner/task pairs, not distinct tasks or learners.

**Competencies:** counts eligible learner/skill slots. Active current-class catalog skills plus skills with retained period observations from a previous class are included. The latest observation by date, then observation ID, determines the selected-period level. Older observations do not increase the assessed-slot count. No evidence means Not assessed; no eligible catalog skills means no coverage denominator. Archived skills are excluded, and the current catalog is used even for older periods. Coverage is assessed slots / eligible slots. The four levels remain separate; no numeric rubric mean or official Kenyan curriculum coverage is claimed.

**Analytics:** freshness is reported for every selected learner. Only a Current marker plus a stored calculation timestamp, valid 0–1 probability, recognized support status and recorded assessments contributes to current coverage or support totals. Legacy snapshots without freshness markers are Stale; missing calculations are Pending; invalid Current snapshots are Unavailable. Stale/unavailable predictions never contribute an old support status. Academic source records remain reportable without a working model. Reports never trigger calculations, send notifications, change read cursors or expose probability estimates as locally validated accuracy.

**Comparisons:** the same current learner population is used for both periods, but assessed learners, record counts, recipient work and competency slots can differ. A delta is unavailable when either side has no denominator. Percentage metrics use percentage-point differences, not relative percent change. These are descriptive summaries, not proof of learning gains or intervention effects.

## API and export

Administrator JWT required; teacher and parent requests receive 403.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/admin/reports/options` | Distinct active grade/stream choices |
| GET | `/api/admin/reports/overview` | Summary, grades, classes, subjects, attendance trend, freshness, comparison, methodology and learner page |
| GET | `/api/admin/reports/export.csv` | One CSV dataset over all matching rows |

Overview requires `term` (`Term 1`–`Term 3`) and four-digit `academic_year` (`0001`–`9999`). Optional: `grade_level`, `stream`, `compare_previous=true`, `issue=all`, `limit=50`, `offset=0`. The earliest supported period has no previous comparison. Follow-up issue values: `all`, `needs_calculation`, `no_assessments`, `missing_work`, `competency_gaps`.

CSV accepts the same period/grade/stream/issue filters and `dataset=summary|grades|classes|subjects|attendance_trend|learners`. CSV is UTF-8 with BOM, includes period/filter/population/timestamp metadata, flattens count dictionaries into columns, and protects text cells from spreadsheet formula execution. Empty datasets return metadata headers and no data rows. CSVs reflect saved data at download time, which can differ from an earlier on-screen generation. Downloads require authentication; there is no public export URL.

No new schema tables or demo seed are required. Reports use existing explicitly seeded fictional records and do not query private message content, teacher evidence text, attendance remarks, email addresses or phone numbers. The current implementation batches source queries and aggregates in memory for prototype cohorts; large-school load testing, reporting indexes, historical enrollment and curriculum versioning remain further work.

## Rehearsal

From `backend/`, against a separately seeded demo server:

```bash
python -m pytest tests/test_reports.py -q
python -m scripts.browser_reports --base-url http://127.0.0.1:8000
```

The browser script is read-only against school records. It exercises filters, previous-period comparison, all-matching learner CSV download, empty periods, simulated API failure/recovery and desktop/mobile layouts. Screenshots and a fictional learner CSV default to `/tmp/ipd-report-screenshots`. The full regression run passed 161 tests with one existing MySQL-only skip; all 17 report cases passed on isolated MySQL. API tests use disposable databases and verify read-only behavior, authorization, denominators, stale-output suppression and CSV safety. See [validation](validation.md).
