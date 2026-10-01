"""
Train and evaluate the CatBoost at-risk model.

Run prepare_data.py first. This script:
    1. Holds out 20% of students as a test set (grouped, so a student who
       appears in both subjects is never in both train and test).
    2. Cross-validates CatBoost and a logistic regression baseline on the
       training set.
    3. Trains the final CatBoost model and evaluates it on the test set.
    4. Saves the model, its metadata and an evaluation report.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import catboost
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from prepare_data import FEATURE_COLUMNS, PROCESSED_DIR, TARGET_COLUMN


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "reports"

MODEL_FILE = "catboost_at_risk.cbm"
METADATA_FILE = "model_metadata.json"

RANDOM_SEED = 42
DECISION_THRESHOLD = 0.5

CATBOOST_PARAMS = {
    "iterations": 500,
    "learning_rate": 0.03,
    "depth": 4,
    "l2_leaf_reg": 5,
    "loss_function": "Logloss",
    "random_seed": RANDOM_SEED,
    "verbose": False
}


def build_catboost():
    return CatBoostClassifier(**CATBOOST_PARAMS)


def build_baseline():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000)
    )


def evaluate(y_true, probabilities):
    predictions = (probabilities >= DECISION_THRESHOLD).astype(int)

    return {
        "roc_auc": roc_auc_score(y_true, probabilities),
        "pr_auc": average_precision_score(y_true, probabilities),
        "accuracy": accuracy_score(y_true, predictions),
        "precision": precision_score(y_true, predictions, zero_division=0),
        "recall": recall_score(y_true, predictions),
        "f1": f1_score(y_true, predictions),
        "brier_score": brier_score_loss(y_true, probabilities),
        "log_loss": log_loss(y_true, probabilities)
    }


def split_train_test(data):
    """Use one fold of a grouped, stratified 5-fold split as the test set."""
    splitter = StratifiedGroupKFold(
        n_splits=5,
        shuffle=True,
        random_state=RANDOM_SEED
    )

    train_index, test_index = next(
        splitter.split(
            data[FEATURE_COLUMNS],
            data[TARGET_COLUMN],
            groups=data["student_group"]
        )
    )

    return data.iloc[train_index], data.iloc[test_index]


def cross_validate(train, model_builders):
    splitter = StratifiedGroupKFold(
        n_splits=5,
        shuffle=True,
        random_state=RANDOM_SEED
    )

    scores = {name: [] for name in model_builders}

    for fold_train, fold_valid in splitter.split(
        train[FEATURE_COLUMNS],
        train[TARGET_COLUMN],
        groups=train["student_group"]
    ):
        x_train = train.iloc[fold_train][FEATURE_COLUMNS]
        y_train = train.iloc[fold_train][TARGET_COLUMN]
        x_valid = train.iloc[fold_valid][FEATURE_COLUMNS]
        y_valid = train.iloc[fold_valid][TARGET_COLUMN]

        for name, builder in model_builders.items():
            model = builder()
            model.fit(x_train, y_train)
            probabilities = model.predict_proba(x_valid)[:, 1]
            scores[name].append(evaluate(y_valid, probabilities))

    return {
        name: {
            metric: {
                "mean": float(np.mean([fold[metric] for fold in folds])),
                "std": float(np.std([fold[metric] for fold in folds]))
            }
            for metric in folds[0]
        }
        for name, folds in scores.items()
    }


def plot_evaluation(y_test, catboost_probs, baseline_probs, importances):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))

    for label, probabilities in [
        ("CatBoost", catboost_probs),
        ("Logistic regression", baseline_probs)
    ]:
        fpr, tpr, _ = roc_curve(y_test, probabilities)
        auc = roc_auc_score(y_test, probabilities)
        axes[0].plot(fpr, tpr, label=f"{label} (AUC {auc:.3f})")

        observed, predicted = calibration_curve(
            y_test, probabilities, n_bins=8, strategy="quantile"
        )
        axes[1].plot(predicted, observed, marker="o", label=label)

    axes[0].plot([0, 1], [0, 1], linestyle="--", color="grey")
    axes[0].set_title("ROC curve (test set)")
    axes[0].set_xlabel("False positive rate")
    axes[0].set_ylabel("True positive rate")
    axes[0].legend(loc="lower right")

    axes[1].plot([0, 1], [0, 1], linestyle="--", color="grey",
                 label="Perfect calibration")
    axes[1].set_title("Calibration (test set)")
    axes[1].set_xlabel("Predicted probability")
    axes[1].set_ylabel("Observed at-risk rate")
    axes[1].legend(loc="upper left")

    ordered = importances.sort_values()
    axes[2].barh(ordered.index, ordered.values)
    axes[2].set_title("CatBoost feature importance")
    axes[2].set_xlabel("Importance (%)")

    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "evaluation.png", dpi=150)
    plt.close(fig)


def format_metrics_table(rows):
    metrics = [
        "roc_auc", "pr_auc", "accuracy", "precision",
        "recall", "f1", "brier_score", "log_loss"
    ]
    header = "| Model | " + " | ".join(metrics) + " |"
    divider = "|---" * (len(metrics) + 1) + "|"
    lines = [header, divider]

    for name, values in rows.items():
        cells = []
        for metric in metrics:
            value = values[metric]
            if isinstance(value, dict):
                cells.append(f"{value['mean']:.3f} ± {value['std']:.3f}")
            else:
                cells.append(f"{value:.3f}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    return "\n".join(lines)


def write_report(data, train, test, cv_results, test_results,
                 matrix, importances):
    tn, fp, fn, tp = matrix.ravel()

    report = f"""# CatBoost At-Risk Model — Evaluation Report

Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

## Data

- Source: UCI Student Performance (Cortez & Silva, 2008), mathematics and
  Portuguese classes, two Portuguese secondary schools.
- Records: {len(data)} ({data['student_group'].nunique()} unique students)
- Target: `at_risk` = final grade below 10/20
  ({data[TARGET_COLUMN].mean():.1%} of records)
- Train: {len(train)} records, test: {len(test)} records. The split is
  grouped by student, so no student appears in both sets.

## Features

| Feature | Dashboard source |
|---|---|
| `first_term_pct` | Assessment percentage, first period |
| `latest_term_pct` | Assessment percentage, latest period |
| `grade_trend` | latest − first |
| `cohort_percentile` | CohortPercentile.percentile_rank |
| `absences` | Attendance records with status Absent |

## Cross-validation (training set, 5 grouped folds, mean ± std)

{format_metrics_table(cv_results)}

## Held-out test set

{format_metrics_table(test_results)}

Decision threshold for accuracy, precision, recall and F1: {DECISION_THRESHOLD}

### CatBoost confusion matrix (test set)

| | Predicted not at risk | Predicted at risk |
|---|---|---|
| Actually not at risk | {tn} | {fp} |
| Actually at risk | {fn} | {tp} |

## Feature importance

{chr(10).join(f"- `{name}`: {value:.1f}%" for name, value in importances.sort_values(ascending=False).items())}

![Evaluation plots](evaluation.png)

## Limitations

- The data comes from two Portuguese schools (2005–2006) and is graded out
  of 20. The dashboard converts all marks to percentages, but the model has
  not been validated on Kenyan school data.
- `absences` in the source data is counted over the whole school year.
  Early in a term the dashboard will see fewer absences than the model was
  trained on, which may understate risk.
- Behaviour records and teacher observations are not in the training data.
  They are used by the expert rules, not by this model.
- The model predicts the probability of failing the final assessment. It is
  a support signal for teachers and parents, not a judgement of the student.
"""

    (REPORTS_DIR / "evaluation.md").write_text(report, encoding="utf-8")


def main():
    data = pd.read_csv(PROCESSED_DIR / "training_data.csv")
    train, test = split_train_test(data)

    model_builders = {
        "CatBoost": build_catboost,
        "Logistic regression (baseline)": build_baseline
    }

    print("Cross-validating on training set...")
    cv_results = cross_validate(train, model_builders)

    print("Training final models...")
    model = build_catboost()
    model.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMN])

    baseline = build_baseline()
    baseline.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMN])

    y_test = test[TARGET_COLUMN]
    catboost_probs = model.predict_proba(test[FEATURE_COLUMNS])[:, 1]
    baseline_probs = baseline.predict_proba(test[FEATURE_COLUMNS])[:, 1]

    test_results = {
        "CatBoost": evaluate(y_test, catboost_probs),
        "Logistic regression (baseline)": evaluate(y_test, baseline_probs)
    }

    matrix = confusion_matrix(
        y_test, (catboost_probs >= DECISION_THRESHOLD).astype(int)
    )

    importances = pd.Series(
        model.get_feature_importance(),
        index=FEATURE_COLUMNS
    )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    model.save_model(str(MODELS_DIR / MODEL_FILE))

    metadata = {
        "model_file": MODEL_FILE,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "catboost_version": catboost.__version__,
        "feature_columns": FEATURE_COLUMNS,
        "target": "at_risk: final grade below 50%",
        "decision_threshold": DECISION_THRESHOLD,
        "training_records": len(train),
        "test_records": len(test),
        "parameters": CATBOOST_PARAMS,
        "test_metrics": {
            name: round(float(value), 4)
            for name, value in test_results["CatBoost"].items()
        }
    }
    (MODELS_DIR / METADATA_FILE).write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    plot_evaluation(y_test, catboost_probs, baseline_probs, importances)
    write_report(data, train, test, cv_results, test_results,
                 matrix, importances)

    print()
    print("Cross-validation:")
    print(format_metrics_table(cv_results))
    print()
    print("Test set:")
    print(format_metrics_table(test_results))
    print()
    print("Confusion matrix (CatBoost):")
    print(matrix)
    print()
    print("Feature importance:")
    print(importances.sort_values(ascending=False).round(1))
    print()
    print(f"Model saved to {(MODELS_DIR / MODEL_FILE).relative_to(BASE_DIR)}")
    print(f"Report saved to {(REPORTS_DIR / 'evaluation.md').relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
