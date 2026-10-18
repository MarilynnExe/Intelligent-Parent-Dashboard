# Intelligent Parent Dashboard

An intelligent web-based parent dashboard system for monitoring learner development using CatBoost, percentile analysis and a rule-based expert system.

Teachers record assessments, attendance, behaviour and observations. The system compares each student with their cohort, estimates the probability that they need support, turns that into intervention advice using expert rules, and communicates it to parents without overwhelming them.

```text
Teacher input ─► Assessments / Attendance / Behaviour
                          │
                          ▼
                 Cohort percentile analysis
                          │
                          ▼
                 CatBoost support probability
                          │
                          ▼
                 Expert-based intervention rules
                          │
                          ▼
                 Adaptive parent communication
```

## Progress tracker

| Stage | Area | Status |
|---|---|---|
| 1 | Project structure, FastAPI backend, MySQL connection, configuration | ✅ Done |
| 2 | JWT authentication and role-based access (Admin, Teacher, Parent) | ✅ Done |
| 2 | Login page and shared frontend API client (`api.js`) | ✅ Done |
| 2 | Admin, teacher and parent dashboards | ✅ Done |
| 3 | Student, parent and teacher relationship models | ✅ Done |
| 3 | Assessment, attendance, behaviour, observation and analytics models | ✅ Done |
| 3 | Cohort percentile service | ✅ Done |
| 3 | Teacher API routes (students, assessments, attendance, behaviour, observations) | ✅ Done |
| 3 | CatBoost training pipeline and evaluation (`ml_training/`) | ✅ Done |
| 3 | CatBoost backend service (load model, calibrate, store probability) | ✅ Done |
| 3 | Code review fixes (router syntax, package files, token errors, frontend paths) | ✅ Done |
| 3 | Security and validation hardening | 🚧 In progress |
| 3 | Admin API (students, teacher assignments, parent links) | ✅ Done |
| 4 | Expert-based intervention rules | ✅ Done |
| 4 | Adaptive parent communication | ⏳ Planned |
| 4 | Teacher monitoring workflow (UI → database → analytics) | ✅ Done |
| 4 | Functional audit fixes (live percentiles, term-scoped absences, input validation, admin UI, behaviour & notes UI, term picker) | ✅ Done |
| 4 | Parent dashboard with intelligent insights | ✅ Done |

## CatBoost model

Trained on the UCI Student Performance dataset (1,044 records, 662 students) to predict whether a student is at risk of failing (final grade below 50%). It is an early-warning model: it only uses three indicators the dashboard can compute from a single term of its own data, in this order:

1. Term assessment average (%)
2. Cohort percentile within the learner's grade and stream
3. Absences in the term, scaled to a full-year count

Raw CatBoost probabilities are calibrated with Platt scaling before they are shown.

Held-out test set (209 records, grouped by student):

| Metric | CatBoost (calibrated) | Logistic regression baseline |
|---|---|---|
| ROC AUC | 0.960 | 0.953 |
| Accuracy | 90.0% | 90.4% |
| Recall (at-risk) | 73.9% | 76.1% |
| Precision (at-risk) | 79.1% | 79.6% |
| Brier score | 0.067 | 0.070 |

CatBoost ranks learners slightly better (higher ROC AUC) and is better calibrated (lower Brier score); the baseline is marginally ahead at the 0.5 threshold. Full results and limitations: [ml_training/reports/evaluation.md](ml_training/reports/evaluation.md)

## Project structure

```text
backend/        FastAPI application (core, models, schemas, routers, services)
frontend/       HTML, CSS and JavaScript dashboards
database/       SQL seed data
ml_training/    Data preparation, model training, saved model and reports
```

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r ml_training/requirements.txt

# Train the model
cd ml_training
python prepare_data.py
python train_catboost.py

# Start the API (from backend/, with DATABASE_URL and JWT_SECRET_KEY in backend/.env)
cd ../backend
uvicorn app.main:app --reload
```

## Running the tests

```bash
cd backend
python -m pytest tests -q
```

The tests use a temporary SQLite database, so they never touch the MySQL database in `backend/.env`.

## Data source

P. Cortez and A. Silva. *Using Data Mining to Predict Secondary School Student Performance.* 2008. UCI Machine Learning Repository, CC BY 4.0.
