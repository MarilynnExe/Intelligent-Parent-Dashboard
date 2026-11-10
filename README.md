# Intelligent Parent Dashboard

A demonstration prototype for learner monitoring with FastAPI, vanilla JavaScript, MySQL, CatBoost, cohort percentiles and expert intervention rules.

**Model scope:** the saved model estimates academic-failure risk on the Portuguese UCI Student Performance benchmark. Its probability is displayed as an advisory support indicator. It has not been validated on Kenyan learners and does not predict behavioural outcomes. Behaviour contributes to separate expert rules. Fictional demo records demonstrate software functionality; they are not training or validation data.

## Quick start

Python 3.12 is the tested interpreter. Create a fresh environment on your machine; the existing `backend/.venv` contains Windows files and cannot run on Linux.

From this project directory:

```bash
python3 -m venv backend/.venv-linux
source backend/.venv-linux/bin/activate
python -m pip install -r backend/requirements-demo.lock
```

The lock file reproduces the tested runtime and test/browser dependencies. For development with flexible versions use `backend/requirements-dev.txt`; `backend/requirements.txt` contains runtime dependencies only.

Create a local MySQL database and an account allowed to create/read/write tables in it. Configure `backend/.env` using `backend/.env.example` as a template, or export `DATABASE_URL` and `JWT_SECRET_KEY` in the shell. Existing environment variables take precedence. Do not overwrite existing credentials unnecessarily.

```bash
cd backend
# Explicitly adds fictional demo data; skips matching records and never resets passwords.
python -m scripts.seed_demo --term 'Term 3' --year 2026 --with-assignments --with-competencies --with-messages
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/portal/login.html**. The frontend and API are served together; there is no npm build or separate static server. For a different port, change the uvicorn argument and open that port; `/portal/` uses the same origin automatically. Keep demo accounts on a local demonstration database.

| Role | Username | Initial password |
|---|---|---|
| Administrator | `demo.admin` | `DemoSchool2026!` |
| Teacher | `demo.teacher` | `DemoSchool2026!` |
| Parent | `demo.parent` | `DemoSchool2026!` |

Choose **Term 3 / 2026** in the dashboards. The seed defaults to the current calendar period when arguments are omitted. It creates three assessed learners, a linked learner without assessments, and a learner outside the teacher's class. Repeating it adds missing fixtures, preserves existing records/passwords and recalculates demo analytics; it is not a database reset. Name/admission collisions with unrelated records abort before data writes.

The model and calibrator are already included. Retraining is not required to run the demo. Optional training uses the separate `ml_training/requirements.txt` and scripts; do not retrain on fictional demo records.

## Implemented demonstration workflow

1. Teachers save assessments, daily attendance or behaviour records.
2. The save transaction marks affected analytics stale and persists the source records.
3. The shared service recalculates the learner's probability and recommendations. Assessment changes also recalculate the grade/stream cohort because classmates' percentiles can change.
4. Successful calculations update learning paths and adaptive notifications for linked parents and assigned teachers.
5. Parents select a learner, term and year to see recorded scores, attendance history, recommendations and calculation time. Visible pages poll every 30 seconds and support manual refresh.

If calculation fails, teacher records remain saved. The API withholds stale probability, percentile and recommendation outputs. Teachers open **Analyze Risk → Recalculate** to retry. Parents see an explanation rather than an old probability presented as current. A learner without assessments remains pending, with attendance still visible.

## Architecture and API

```text
Teacher save → source records + stale marker → shared analytics service
    → cohort percentiles → calibrated CatBoost → expert rules / learning paths
    → current marker → adaptive in-app notifications → parent dashboard
```

- `backend/`: FastAPI, SQLAlchemy models, services, tests and explicit demo scripts.
- `frontend/`: buildless HTML/CSS/JavaScript; asset directory is uppercase `JS/`.
- `ml_training/`: UCI preparation/training code, saved artifacts and evaluation report.
- `database/`: existing SQL fixtures; use the Python seed for the rehearsed demonstration.

Interactive API documentation: **http://127.0.0.1:8000/docs**. JWT role and learner-link checks protect data; parents cannot trigger calculations or access unlinked learners.

Existing endpoints remain available. Additions:

- `GET /api/parent/children/{id}/progress?term=Term%203&academic_year=2026`: period-filtered assessment history, live recorded average, attendance totals/monthly counts and freshness metadata.
- Analytics responses add `freshness`, `is_current` and `freshness_message`. Non-current snapshots withhold dependent results. `calculated_at` identifies the last calculated snapshot, not the last teacher save.
- Assessment save responses add `analytics_refresh`; attendance and behaviour saves return per-learner refresh outcomes. `POST /api/analytics/calculate/{id}` retries the affected cohort and returns the requested learner's result.

The new `analytics_freshness` table is created on application/seed startup using SQLAlchemy's existing table-creation mechanism. Existing analytics tables are not altered. CRUD completion also adds `user_lifecycle`, `student_lifecycle` and `record_changes` to support deactivation, archiving and correction history without altering legacy columns. Legacy snapshots without freshness records are treated as stale until recalculated. Run this with a database account that can create the new table. No source data is deleted.

## Phase 2A: Assignment tracking

Teachers can now create class-wide assignments, record completion, require reasons for late submissions, and edit/withdraw/restore work. Parents see automatic missing status after the deadline, completion rates and specific follow-up guidance. New learners receive open work automatically. These records do not change CatBoost inputs or assessment averages. See [assignment tracking](docs/assignment-tracking.md) for the full workflow and API.

## Phase 2B: Competency tracking

Teachers can define class/subject skills, record dated four-level evidence, correct/delete observations and archive/restore skills. Parents see latest demonstrated levels, evidence history, changes and separate practice guidance. Unassessed skills are explicit; no competency evidence enters CatBoost. The catalog is teacher-defined, with no verified official curriculum mapping. See [competency tracking](docs/competency-tracking.md).

For the current implementation, setup, model boundaries and remaining roadmap, see the [project handover](docs/HANDOVER.md), also available as [Word](docs/HANDOVER.docx) and [PDF](docs/HANDOVER.pdf).

## Phase 2C: Private messaging

Parents and teachers can start private learner-specific text conversations, reply, review paginated history and track unread/read status. Visible conversations refresh every 30 seconds. Current links are required for replies; original participants retain read-only history after links end. Administrators cannot read message content. Send retries are idempotent, and notification failures preserve messages. See [messaging](docs/messaging.md).

## Phase 2D: School-wide reporting

Administrators can review period-filtered school, grade, class and subject summaries, attendance trends, assignment/competency coverage, analytics freshness, previous-term comparisons and a learner follow-up register. CSV exports include all matching rows. Reports are read-only, exclude archived learners and stale support outputs, and clearly label current-enrollment and recorded-data denominators. See [school reports](docs/school-reports.md).

## Editing and removal

Administrators can edit accounts and learners, deactivate/restore accounts, archive/restore learners, and edit teaching assignments and parent links. Teachers can correct/delete assessments, behaviour ratings and observations, and load/correct/delete saved attendance entries. Deactivation invalidates sessions; archived learners are excluded from active monitoring. Source corrections refresh dependent analytics and retain protected history. See [CRUD completion](docs/crud-audit.md) for exact permissions, APIs and usage.

## Tests and rehearsal

From `backend/` with the environment activated:

```bash
python -m pytest tests -q
# Optional browser rehearsal; first run the seeded local server above.
python -m playwright install chromium
python -m scripts.browser_demo --base-url http://127.0.0.1:8000
```

Tests always use temporary SQLite databases via `tests/conftest.py` and dependency overrides; they do not reset your configured MySQL database. Browser rehearsal intentionally adds an assessment to the fictional demo learner; use a demo database seeded for Term 3 / 2026. Screenshots default to `/tmp/ipd-demo-screenshots`; override with `--screenshots PATH`.

See [the CRUD audit](docs/crud-audit.md) for the completed edit, removal, archive/restore and attendance workflows.

See [the demo guide](docs/demo-guide.md) for presentation steps and [validation results](docs/validation.md) for checks performed and limitations.

## Benchmark evaluation and boundaries

The model uses three inputs in this order: term assessment average (%), grade/stream cohort percentile, and term absences scaled to the benchmark's full-year horizon. Term-to-year scaling is a prototype assumption. The training target is UCI final grade `G3 < 10/20`, not a Kenyan grading or competency threshold. Applying the same benchmark model to later terms is an extrapolation, not a separately validated model.

Reported held-out results: accuracy **89.95%**, precision **79.07%**, recall **73.91%**, F1 **76.40%**, ROC AUC **0.9599**. These are benchmark results, not measured Kenyan performance. Full methodology and calibration limitations: [evaluation report](ml_training/reports/evaluation.md). No model was retrained for this demonstration.

The implementation retains Python/FastAPI and vanilla JavaScript instead of the proposal's Node.js/Express and React. The project is a prototype demonstration, not full proposal compliance or a school production deployment. Historical enrollment/curriculum versioning, verified official curriculum mapping, intervention outcome tracking and Kenyan validation remain future work. Recalculation is synchronous and intended for small demonstration cohorts; background jobs and multi-user concurrency hardening are future pilot work.
