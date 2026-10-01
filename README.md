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
| 3 | Teacher, attendance and behaviour API routes | 🚧 Written, not yet registered in `main.py` |
| 3 | CatBoost training pipeline and evaluation (`ml_training/`) | ✅ Done |
| 3 | CatBoost backend service (load model, store probability) | 🚧 Next |
| 4 | Expert-based intervention rules | ⏳ Planned |
| 4 | Adaptive parent communication | ⏳ Planned |
| 4 | Teacher monitoring workflow (UI → database → analytics) | ⏳ Planned |
| 4 | Parent dashboard with intelligent insights | ⏳ Planned |

## CatBoost model

Trained on the UCI Student Performance dataset (1,044 records, 662 students) to predict whether a student is at risk of failing (final grade below 50%). Only features the dashboard can compute from its own data are used: first and latest term percentages, grade trend, cohort percentile and absences.

Held-out test set (209 records, grouped by student):

| Metric | CatBoost | Logistic regression baseline |
|---|---|---|
| ROC AUC | 0.977 | 0.973 |
| Accuracy | 91.9% | 91.4% |
| Recall (at-risk) | 76.1% | 73.9% |
| Precision (at-risk) | 85.4% | 85.0% |
| Brier score | 0.052 | 0.056 |

Full results and limitations: [ml_training/reports/evaluation.md](ml_training/reports/evaluation.md)

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

## Data source

P. Cortez and A. Silva. *Using Data Mining to Predict Secondary School Student Performance.* 2008. UCI Machine Learning Repository, CC BY 4.0.
