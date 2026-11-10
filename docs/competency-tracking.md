# Competency tracking — Phase 2B

Teachers define classroom skills for an assigned grade, stream and subject. They record **dated, explicit evidence** at one of four levels: Below expectations, Approaching expectations, Meeting expectations, or Exceeding expectations. No evidence is **Not assessed**, never zero or Below expectations. The catalog is teacher-defined; this release does not verify an official Kenyan curriculum mapping.

## Teacher workflow

1. Select a teaching assignment and year/term, then open **Competency tracking**.
2. Add a skill, optional strand/topic, and a description of what demonstrating it looks like. Catalog skills span terms; evidence is term-specific.
3. Open **Evidence register** and **Record evidence** for a learner. Enter the observation date, demonstrated level and concrete evidence/support needs. Dates must be in the selected period and cannot be in the future (Africa/Nairobi).
4. Add a later observation to show progress. Use **Correct evidence** for mistakes, or **Delete evidence** to remove an erroneous observation. Administrators retain protected before/after correction history.
5. Edit skill descriptions or archive/restore skills. Archiving hides a skill from active parent summaries and preserves evidence; restoring reveals it again. Archived skills are read-only until restored.

Teachers require a current class/subject assignment for every request. Only active learners currently in the competency's class can have evidence added/corrected/deleted. A transferred learner's existing evidence remains available to their linked parent, labeled previous-class history. The old class register no longer lists that learner. This release has no full historical enrollment register; administrators can inspect correction history.

## Parent experience and interpretation

The **Competencies** tab uses the same learner, year and term as the other monitoring views. It updates during the visible page's 30-second refresh and through **Refresh progress**, without another sign-in. Only linked active learners are accessible to parents. Administrators can read summaries through the API.

For each active skill the summary shows the latest recorded level, date, evidence and expandable dated history. Latest means observation date, then observation ID for same-day ties; entering an older observation does not replace newer evidence. A change label compares the latest two observations in the selected period. This is a recorded rubric comparison, not a prediction or a measured rate of learning. Current-class skills with no selected-period evidence appear as Not assessed; catalog creation is not restricted to a term, so historical views can include unassessed skills added later.

Below/Approaching evidence generates separate skill-specific practice guidance. It does not imply a diagnosis, infer topic weaknesses from an examination mark, or establish official curriculum coverage. No ordinal numeric average is calculated. Archived skills are omitted from active counts; their history returns after restoration.

Competency writes do **not** change academic assessment averages, cohort percentiles, the CatBoost feature set, model weights or stored prediction snapshots. They work without assessments or a working prediction model.

## Follow-up notifications

Teacher observation saves/corrections/deletions and competency archive/restore refresh support follow-ups for linked parents. Alerts use the existing ACADEMIC preference and MEDIUM priority, with detailed/concise preferences and per-parent/learner/period duplicate suppression. Unread alerts update in place; recently read matches retain the existing 24-hour cooldown. When no active skills need practice, a matching unread support alert is marked read. This release alerts on support needs rather than sending an alert for every positive observation.

Teacher records are committed before delivery. Delivery failure returns `notification_delivery.status=retry_needed`, displays a saved-records/retry message, and can be retried using **Retry follow-up alerts**. There are no scheduled competency reminders or durable background delivery jobs.

## API

All paths are under `/api`; JWT authorization is required.

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/teacher/competencies` | List / define class-subject skills |
| PUT / DELETE | `/teacher/competencies/{id}` | Edit details / archive |
| PATCH | `/teacher/competencies/{id}/status` | Archive or restore (`is_archived`) |
| GET | `/teacher/competencies/{id}/register?term=...&academic_year=...` | Active class learners and dated evidence |
| POST | `/teacher/competencies/{id}/observations` | Add learner evidence |
| PUT / DELETE | `/teacher/competency-observations/{id}` | Correct / delete evidence |
| POST | `/teacher/competencies/{id}/notify?term=...&academic_year=...` | Retry period follow-ups |
| GET | `/parent/children/{id}/competencies?term=...&academic_year=...` | Authorized period summary |

Catalog list query: `grade_level`, `stream`, `subject_name`, optional `include_archived`. Skill class/subject are fixed after creation. Observation creation includes `student_id`, `term`, `academic_year`, `observed_on`, `level`, `evidence`; corrections cannot move evidence to another learner or skill. Corrections can move periods and refresh follow-ups in both periods.

The additive `competencies` and `competency_observations` tables are registered on startup. No legacy tables or model artifacts are modified. Audit uses the existing `record_changes` table.

## Fictional examples

From `backend/`, against a demo database:

```bash
python -m scripts.seed_demo --term 'Term 3' --year 2026 --with-assignments --with-competencies
```

The explicit flag adds three fictional Mathematics skills for Demo East. Amina and David show fractions improving to Meeting expectations, number patterns needing practice, and practical problems Not assessed. Repeat runs preserve existing skill/evidence corrections and do not refill deleted evidence. Seed competency observations are created only when a fixture skill is first created; this is a demo fixture, not a multi-year curriculum loader. Future-period observation seeding is rejected. These are not training data.
