# Demonstration guide

Use a local database containing fictional demo records, not real learner data. Start the application and seed Term 3 / 2026 as described in the README. All three demo accounts initially use `DemoSchool2026!`.

## Present the core workflow

1. Sign in as `demo.admin`. Inspect the user list, five fictional students, two teacher subject assignments and parent links. The teacher has Grade 7 / Demo East only. The parent is linked to Amina Demo and David Demo. Existing admin workflows can add another learner, teacher assignment or parent link.
2. Open a separate browser profile/private window as `demo.parent`. Select Amina, Term 3 / 2026. Explain the benchmark scope shown below the probability. Note the current average and last calculation time.
3. In another profile sign in as `demo.teacher`. Select Grade 7 / Demo East, Term 3 / 2026. Open Assessments and save a new Mathematics CAT for Amina, for example 96/100 dated 25 September 2026.
4. Show the refreshed teacher roster. Return to the parent window and wait up to 30 seconds, or click **Refresh progress**. The average, advisory estimate, recommendations and calculation time update without signing in again. Classmates' percentile-dependent predictions also refresh.
5. Open Academic Performance to show date-ordered score observations grouped by subject. Open Attendance to show recorded totals and monthly counts. These are recorded observations; unrecorded days are not assumed present.
6. Open the notification bell. Show academic/support, attendance and classroom guidance. Preferences support concise/detailed text and optional categories. High-priority advisories bypass preference suppression. Unread matching alerts update in place; recently read matching alerts are suppressed for 24 hours after reading.
7. As teacher, record or correct attendance and save a low behaviour rating in the selected term. Records automatically refresh analytics. Behaviour affects expert guidance, not the CatBoost feature vector.
8. Select David in the parent portal: no assessments means a pending prediction, without fabricated scores. Switch to an empty year to show the empty-period view. Restore the demo period.

## Retry and failure behaviour

When artifacts are unavailable or a calculation fails, records remain saved. The teacher sees that calculation needs a retry. Open a learner's **Analyze Risk** view and use **Recalculate** after resolving the model problem. Do not remove or replace the real artifacts during a live presentation; automated regression tests exercise the failure path without changing them.

The parent sees unavailable/pending guidance and the last calculation time, while live assessment and attendance history remain accessible. Previous recommendations and probabilities are withheld while stale. A failed network refresh clears guidance and offers manual refresh. Repeated recalculation should not add duplicate alerts.

## Accounts, permissions and interpretation

- Administrators manage users, students, teaching assignments and parent links.
- Teachers can record data only for assigned classes/subjects; the fictional Demo West student is outside the demo teacher's permissions.
- Parents view only linked learners. They cannot write teacher data or request model recalculation.
- Percentiles compare the selected grade/stream and period; peers' identities and scores are not exposed to parents.
- The advisory number estimates academic-failure risk learned from UCI Portuguese records. There is no Kenyan accuracy claim. A low value is not proof of learner wellbeing, and behaviour guidance is generated separately from recorded observations.

## Operational notes

- Serve `/portal/login.html` through FastAPI; do not open HTML files directly from disk.
- Environment variables override `.env`. The startup adds the freshness table; it does not migrate or delete source records.
- The seed is additive and does not reset previously changed passwords. Repeated browser rehearsals add assessments, so averages will differ between runs.
- Term windows are fixed prototype buckets: January–April, May–August, September–December. They include holidays and are not an official school timetable.
- Use the automated API tests and browser rehearsal in the README before presenting. A real usability study, production load testing and Kenyan validation are outside this demo's evidence.


## Corrections and lifecycle controls

The previously missing edit/removal workflows are now available. Follow the [CRUD completion guide](crud-audit.md) to demonstrate admin edits, deactivate/archive and restore, relationship edits, teacher corrections/deletions and loading saved attendance. Account deactivation/password reset ends existing sessions. Learner archiving preserves source records while hiding active monitoring access. Attendance no longer assumes unrecorded learners are present; select a status or use Mark All as Present before saving.


## Assignment completion

Phase 2A adds a separate Assignments workflow. Seed with `--with-assignments` and follow the [assignment tracking guide](assignment-tracking.md). Demonstrate automatic missing status, a late submission with a reason, withdrawal/restoration, and the parent completion summary. Assignment completion affects expert guidance and alerts; scored assessments remain the only academic-score inputs to CatBoost.

## Competency demonstration

Seed with `--with-competencies` and open **Competency tracking** as the teacher. Show the teacher-defined skill catalog, dated four-level evidence, a correction and archive/restore. As parent, open **Competencies** and review the evidence history, latest level, change label and practice guidance; David demonstrates this without academic assessment data. The unassessed skill is not a failing score. See [competency tracking](competency-tracking.md) and the [project handover](HANDOVER.md). These records do not change CatBoost predictions.


## Private messaging demonstration

Seed explicitly with `--with-messages`, then open **Messages** in separate parent and teacher browsers. Select Amina and the eligible contact, send a message and wait for the other visible conversation's 30-second refresh. Reply and show Read labels. Explain that failed network responses can be safely retried, that alerts contain no text previews, and that former participants retain read-only history after relationships end. This is private to the pair; another parent and the administrator have no content access. See [messaging](messaging.md).


## School-wide reporting demonstration

As administrator, open **School Reports**, choose the demo period and generate a report. Show school/class/subject figures, attendance trends, previous-term coverage context and freshness counts. Filter to Demo West to show a learner without assessments, then use the learner follow-up filter and CSV export. Explain that unrecorded attendance is not absence, unassessed skills are not zero scores, and only current stored predictions count toward advisory support totals. See [school reports](school-reports.md).
