"""
Train and evaluate the early-warning CatBoost at-risk model.

This script implements the corrected, leakage-free ML pipeline (ML-3):
    1. Outer split: Holds out 20% of students as a locked test set using
       StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42) on
       13 student identity attributes (662 unique student groups). Zero group overlap.
    2. Fold-specific cohort percentile calculation: Percentile ranks are strictly
       derived from Period 1 grades (first_term_pct) within the reference fold,
       preventing any cross-fold or test-set leakage.
    3. Inner cross-validation & Out-of-Fold (OOF) Calibration:
       Within the 80% Development Pool (N=835), a 4-fold StratifiedGroupKFold
       generates leak-free out-of-fold probability predictions. A Platt scaling
       calibrator (LogisticRegression) is fitted on these OOF predictions.
    4. Model training: Trains the final CatBoost model on the full Development Pool.
    5. Evaluation: Compares Prevalence Baseline, Logistic Regression baseline,
       Uncalibrated CatBoost, and Calibrated CatBoost on the locked test set (N=209).
    6. Reporting: Generates model metadata, calibration analysis, evaluation plots,
       and a detailed evaluation report.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import catboost
import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
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
    roc_curve,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from prepare_data import FEATURE_COLUMNS, PROCESSED_DIR, TARGET_COLUMN


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "reports"

MODEL_FILE = "catboost_at_risk.cbm"
CALIBRATOR_FILE = "probability_calibrator.joblib"
METADATA_FILE = "model_metadata.json"

RANDOM_SEED = 42
DECISION_THRESHOLD = 0.5

CATBOOST_PARAMS = {
    "iterations": 300,
    "learning_rate": 0.03,
    "depth": 4,
    "l2_leaf_reg": 5.0,
    "loss_function": "Logloss",
    "random_seed": RANDOM_SEED,
    "verbose": False,
}


def compute_cohort_percentile(ref_df: pd.DataFrame, target_df: pd.DataFrame) -> pd.Series:
    """
    Compute cohort percentile for target_df using strictly ref_df as the reference distribution.
    Cohort is defined by (school, subject).
    Formula: round(((ref_scores < score).sum() + 0.5 * (ref_scores == score).sum()) / N * 100, 1)
    """
    percentiles = pd.Series(index=target_df.index, dtype=float)
    for (school, subject), group in target_df.groupby(["school", "subject"]):
        ref_mask = (ref_df["school"] == school) & (ref_df["subject"] == subject)
        ref_scores = ref_df.loc[ref_mask, "first_term_pct"].to_numpy()
        if len(ref_scores) == 0:
            ref_scores = ref_df["first_term_pct"].to_numpy()
        n = len(ref_scores)

        def rank_score(score):
            return round(
                ((ref_scores < score).sum() + 0.5 * (ref_scores == score).sum()) / n * 100,
                1,
            )

        percentiles.loc[group.index] = group["first_term_pct"].apply(rank_score)

    return percentiles


def build_catboost():
    return CatBoostClassifier(**CATBOOST_PARAMS)


def build_baseline():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, random_state=RANDOM_SEED),
    )


def evaluate(y_true, probabilities, threshold=DECISION_THRESHOLD):
    probabilities = np.clip(probabilities, 1e-15, 1 - 1e-15)
    predictions = (probabilities >= threshold).astype(int)

    # Handle constant probability baseline (e.g. prevalence baseline) for ROC-AUC
    if len(np.unique(probabilities)) == 1:
        roc_auc = 0.5
    else:
        roc_auc = float(roc_auc_score(y_true, probabilities))

    return {
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "log_loss": float(log_loss(y_true, probabilities)),
        "roc_auc": roc_auc,
        "pr_auc": float(average_precision_score(y_true, probabilities)),
        "accuracy": float(accuracy_score(y_true, predictions)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions)),
        "f1": float(f1_score(y_true, predictions)),
    }


def split_outer_train_test(data):
    """
    Split into 80% Development pool and 20% Locked Test set using StratifiedGroupKFold.
    Ensures zero student overlap between Dev and Test.
    """
    splitter = StratifiedGroupKFold(
        n_splits=5,
        shuffle=True,
        random_state=RANDOM_SEED,
    )

    train_idx, test_idx = next(
        splitter.split(
            data[FEATURE_COLUMNS],
            data[TARGET_COLUMN],
            groups=data["student_group"],
        )
    )

    dev_df = data.iloc[train_idx].copy().reset_index(drop=True)
    test_df = data.iloc[test_idx].copy().reset_index(drop=True)

    # Verification: disjoint groups
    overlap = set(dev_df["student_group"]).intersection(set(test_df["student_group"]))
    assert len(overlap) == 0, f"Error: Student group leakage detected! Overlapping groups: {len(overlap)}"

    return dev_df, test_df


def cross_validate_and_get_oof(dev_df):
    """
    Run 4-fold StratifiedGroupKFold on Development Pool to:
    1. Collect out-of-fold raw probabilities from CatBoost for Platt calibration.
    2. Compute inner CV metrics for CatBoost and Logistic Regression.
    """
    inner_splitter = StratifiedGroupKFold(
        n_splits=4,
        shuffle=True,
        random_state=RANDOM_SEED,
    )

    oof_raw_probs = np.zeros(len(dev_df), dtype=float)
    cv_scores = {"CatBoost": [], "Logistic regression (baseline)": []}

    for fold_idx, (train_idx, val_idx) in enumerate(
        inner_splitter.split(
            dev_df[FEATURE_COLUMNS],
            dev_df[TARGET_COLUMN],
            groups=dev_df["student_group"],
        )
    ):
        fold_train = dev_df.iloc[train_idx].copy()
        fold_val = dev_df.iloc[val_idx].copy()

        # Fold-specific leak-free cohort percentiles
        fold_train["cohort_percentile"] = compute_cohort_percentile(fold_train, fold_train)
        fold_val["cohort_percentile"] = compute_cohort_percentile(fold_train, fold_val)

        x_train = fold_train[FEATURE_COLUMNS]
        y_train = fold_train[TARGET_COLUMN]
        x_val = fold_val[FEATURE_COLUMNS]
        y_val = fold_val[TARGET_COLUMN]

        # CatBoost fold model
        cb = build_catboost()
        cb.fit(x_train, y_train)
        cb_probs = cb.predict_proba(x_val)[:, 1]
        oof_raw_probs[val_idx] = cb_probs
        cv_scores["CatBoost"].append(evaluate(y_val, cb_probs))

        # Baseline fold model
        lr = build_baseline()
        lr.fit(x_train, y_train)
        lr_probs = lr.predict_proba(x_val)[:, 1]
        cv_scores["Logistic regression (baseline)"].append(evaluate(y_val, lr_probs))

    cv_summary = {
        name: {
            metric: {
                "mean": float(np.mean([f[metric] for f in folds])),
                "std": float(np.std([f[metric] for f in folds])),
            }
            for metric in folds[0]
        }
        for name, folds in cv_scores.items()
    }

    return oof_raw_probs, cv_summary


def compute_calibration_bins(y_true, probabilities, n_bins=5):
    """
    Compute calibration metrics across n uniform bins [0, 0.2), [0.2, 0.4), etc.
    """
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_rows = []
    total_samples = len(y_true)
    weighted_abs_error = 0.0
    max_abs_error = 0.0

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask = (probabilities >= low) & (probabilities <= high)
        else:
            mask = (probabilities >= low) & (probabilities < high)

        count = int(mask.sum())
        if count > 0:
            mean_pred = float(np.mean(probabilities[mask]))
            obs_rate = float(np.mean(y_true[mask]))
            abs_err = abs(mean_pred - obs_rate)
            weighted_abs_error += count * abs_err
            max_abs_error = max(max_abs_error, abs_err)
        else:
            mean_pred = float((low + high) / 2)
            obs_rate = 0.0
            abs_err = 0.0

        bin_rows.append({
            "bin": f"[{low:.1f}, {high:.1f}{']' if i == n_bins - 1 else ')'}",
            "count": count,
            "mean_pred": mean_pred,
            "obs_rate": obs_rate,
            "abs_error": abs_err,
        })

    ece = weighted_abs_error / total_samples
    mce = max_abs_error

    return bin_rows, ece, mce


def plot_evaluation(y_test, cb_cal_probs, cb_raw_probs, lr_probs, prev_probs, importances):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))

    # Panel 1: ROC Curve
    for label, probs, color in [
        ("Calibrated CatBoost", cb_cal_probs, "navy"),
        ("Logistic Regression", lr_probs, "darkorange"),
        ("Prevalence Baseline", prev_probs, "gray"),
    ]:
        if len(np.unique(probs)) > 1:
            fpr, tpr, _ = roc_curve(y_test, probs)
            auc = roc_auc_score(y_test, probs)
            axes[0].plot(fpr, tpr, label=f"{label} (AUC {auc:.3f})", color=color, lw=2)
        else:
            axes[0].plot([0, 1], [0, 1], linestyle=":", label=f"{label} (AUC 0.500)", color=color)

    axes[0].plot([0, 1], [0, 1], linestyle="--", color="grey", alpha=0.7)
    axes[0].set_title("ROC Curve (Locked Test Set)", fontsize=11, fontweight="bold")
    axes[0].set_xlabel("False Positive Rate")
    axes[0].set_ylabel("True Positive Rate")
    axes[0].legend(loc="lower right", fontsize=9)
    axes[0].grid(True, alpha=0.3)

    # Panel 2: Reliability Diagram (5 uniform bins)
    axes[1].plot([0, 1], [0, 1], linestyle="--", color="grey", label="Perfect Calibration")

    for label, probs, marker, color in [
        ("Calibrated CatBoost", cb_cal_probs, "o", "navy"),
        ("Uncalibrated CatBoost", cb_raw_probs, "s", "crimson"),
        ("Logistic Regression", lr_probs, "^", "darkorange"),
    ]:
        bins_data, ece, _ = compute_calibration_bins(y_test, probs, n_bins=5)
        # Filter bins with non-zero count for plotting points
        valid_bins = [b for b in bins_data if b["count"] > 0]
        preds = [b["mean_pred"] for b in valid_bins]
        obs = [b["obs_rate"] for b in valid_bins]
        axes[1].plot(preds, obs, marker=marker, label=f"{label} (ECE {ece:.3f})", color=color, lw=1.5)

    axes[1].set_title("Calibration Curve (5 Uniform Bins)", fontsize=11, fontweight="bold")
    axes[1].set_xlabel("Mean Predicted Probability")
    axes[1].set_ylabel("Observed At-Risk Rate")
    axes[1].set_xlim([0, 1])
    axes[1].set_ylim([0, 1])
    axes[1].legend(loc="upper left", fontsize=9)
    axes[1].grid(True, alpha=0.3)

    # Panel 3: Feature Importance
    ordered = importances.sort_values(ascending=True)
    axes[2].barh(ordered.index, ordered.values, color="teal", edgecolor="black", alpha=0.8)
    axes[2].set_title("CatBoost Feature Importance", fontsize=11, fontweight="bold")
    axes[2].set_xlabel("Relative Importance (%)")
    for idx, (name, val) in enumerate(ordered.items()):
        axes[2].text(val + 0.5, idx, f"{val:.1f}%", va="center", fontsize=9)
    axes[2].set_xlim([0, max(ordered.values) + 12])
    axes[2].grid(True, axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "evaluation.png", dpi=150)
    plt.close(fig)


def format_metrics_table(rows):
    metrics = [
        "brier_score", "log_loss", "roc_auc", "pr_auc",
        "accuracy", "precision", "recall", "f1"
    ]
    header = "| Model | " + " | ".join(metrics) + " |"
    divider = "|---" * (len(metrics) + 1) + "|"
    lines = [header, divider]

    for name, values in rows.items():
        cells = []
        for metric in metrics:
            value = values[metric]
            if isinstance(value, dict):
                cells.append(f"{value['mean']:.4f} ± {value['std']:.4f}")
            else:
                cells.append(f"{value:.4f}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    return "\n".join(lines)


def write_report(dev_df, test_df, cv_summary, test_results, cal_bins, ece, mce, matrix, importances, calibrator):
    tn, fp, fn, tp = matrix.ravel()
    total_records = len(dev_df) + len(test_df)
    dev_prev = dev_df[TARGET_COLUMN].mean()
    test_prev = test_df[TARGET_COLUMN].mean()

    cal_bins_table_rows = [
        "| Probability Bin | Test Count | Mean Predicted Prob | Observed At-Risk Rate | Absolute Error |",
        "|---|---|---|---|---|"
    ]
    for b in cal_bins:
        cal_bins_table_rows.append(
            f"| {b['bin']} | {b['count']} | {b['mean_pred']:.4f} | {b['obs_rate']:.4f} | {b['abs_error']:.4f} |"
        )
    cal_bins_table = "\n".join(cal_bins_table_rows)

    report = f"""# CatBoost At-Risk Early-Warning Model — Evaluation Report

Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

## 1. Study Overview & Methodological Safeguards

- **Project:** Intelligent Parent Dashboard System for Early Learner Intervention Using CatBoost
- **Problem Formulation:** Early-warning prediction of student academic failure using only data available at Period 1.
- **Dataset:** UCI Student Performance (Cortez & Silva, 2008), combining Mathematics (395 records) and Portuguese (649 records) classes (Total: {total_records} records across 662 unique student identity groups).
- **Target:** `at_risk = 1` if final grade $G3 < 10/20$ (benchmark failure threshold), `0` otherwise.
  - *Context clarification:* The $G3 < 10$ cutoff is strictly an empirical UCI benchmark failure mark under the Portuguese 20-point scale. It is NOT a Kenyan grading, CBC, or KCSE threshold.
- **Leakage Prevention:**
  - $G2$ (second-term assessment) has been completely eradicated from features, eliminating temporal lookahead leakage.
  - All features represent only information available at Period 1.
  - Outer data split uses `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` across 13 student demographic attributes, guaranteeing that the same student appearing in both subjects is never present in both training and test sets.
  - Percentile rankings are computed strictly within training folds, ensuring zero reference-pool leakage.

## 2. Dataset Split & Class Distribution

- **Development Pool:** {len(dev_df)} records ({dev_df['student_group'].nunique()} unique students), At-risk prevalence: {dev_prev:.1%} ({dev_df[TARGET_COLUMN].sum()} at risk).
- **Locked Test Set:** {len(test_df)} records ({test_df['student_group'].nunique()} unique students), At-risk prevalence: {test_prev:.1%} ({test_df[TARGET_COLUMN].sum()} at risk).
- **Student Group Overlap:** Exactly 0 overlapping student identities between Development Pool and Test Set.

## 3. Predictor Set (Period 1 Only)

| Feature | Type | Source & Formula | Dashboard Mapping |
|---|---|---|---|
| `first_term_pct` | Continuous | $G1 / 20 \\times 100$ | First assessment percentage |
| `cohort_percentile` | Continuous | Grouped by `(school, subject)` on `first_term_pct`: $(N_{{<}} + 0.5 N_{{=}}) / N \\times 100$ | CohortPercentile service |
| `absences` | Discrete | Total student absences | Attendance records (status "Absent") |

## 4. Inner Cross-Validation (Development Pool, 4 Grouped Folds)

Metrics across 4 out-of-fold validation splits on the Development Pool (mean ± std):

{format_metrics_table(cv_summary)}

## 5. Locked Test Set Evaluation

Performance of all benchmark models on the untouched test set (N={len(test_df)}):

{format_metrics_table(test_results)}

*Decision threshold for binary metrics (Accuracy, Precision, Recall, F1): {DECISION_THRESHOLD}*

### Calibrated CatBoost Confusion Matrix (Locked Test Set)

| | Predicted Not at Risk ($\\\\hat{{y}}=0$) | Predicted At Risk ($\\\\hat{{y}}=1$) | Total |
|---|---|---|---|
| **Actually Not at Risk ($y=0$)** | {tn} (True Negatives) | {fp} (False Positives) | {tn + fp} |
| **Actually At Risk ($y=1$)** | {fn} (False Negatives) | {tp} (True Positives) | {fn + tp} |
| **Total** | {tn + fn} | {fp + tp} | {len(test_df)} |

## 6. Probability Calibration Analysis (Platt Scaling)

- **Calibrator Architecture:** Sigmoid Platt scaling ($\\\\text{{LogisticRegression}}(C=10^5)$) fitted on 835 Out-of-Fold (OOF) probabilities from inner cross-validation.
- **Calibrator Parameters:** Slope ($w$): {calibrator.coef_[0][0]:.4f}, Intercept ($b$): {calibrator.intercept_[0]:.4f}.
- **Expected Calibration Error (ECE):** {ece:.4f} ({ece * 100:.2f}%)
- **Maximum Calibration Error (MCE):** {mce:.4f} ({mce * 100:.2f}%)

### Reliability Table (5 Uniform Bins on Test Set)

{cal_bins_table}

## 7. Feature Importance (CatBoost)

{chr(10).join(f"- `{name}`: {value:.2f}%" for name, value in importances.sort_values(ascending=False).items())}

## 8. Evaluation Visualizations

![Evaluation Plots](evaluation.png)

## 9. Academic Limitations & Contextual Discussion

1. **Benchmark vs. Deployment Context:** The training data originates from two Portuguese secondary schools (Cortez & Silva, 2008) under a 20-point system. Although normalized to percentages (0-100%), the model has not yet been fine-tuned on Kenyan educational data (CBC / KCSE).
2. **Absences Horizon Limitation:** In the UCI dataset, `absences` reflects full-year cumulative attendance. In live early-warning deployment at Period 1, observed absences will naturally be lower than full-year counts. Calibration adjustments or annualized attendance rates should be considered during live deployment.
3. **Sociological & Behavioral Exclusion:** High-dimensional family and sociological factors were deliberately omitted to ensure strict computability from basic school operational databases and avoid algorithmic demographic bias.
4. **Decision Support Nature:** The model outputs an advisory probability for early parental and teacher intervention, not an autonomous high-stakes academic determination.
"""

    (REPORTS_DIR / "evaluation.md").write_text(report, encoding="utf-8")


def main():
    print("=" * 60)
    print("STARTING ML-3 EARLY-WARNING CATBOOST PIPELINE")
    print("=" * 60)

    # Load prepared data
    data_path = PROCESSED_DIR / "training_data.csv"
    data = pd.read_csv(data_path)
    print(f"Loaded {len(data)} records from {data_path.name}")

    # 1. Outer split (80% dev, 20% test)
    dev_df, test_df = split_outer_train_test(data)
    print(f"Development pool: {len(dev_df)} records ({dev_df['student_group'].nunique()} student groups)")
    print(f"Locked test set:  {len(test_df)} records ({test_df['student_group'].nunique()} student groups)")

    # 2. Inner CV & Out-of-fold predictions on Dev Pool
    print("\nRunning 4-fold inner CV on Development pool for OOF predictions...")
    oof_raw_probs, cv_summary = cross_validate_and_get_oof(dev_df)

    # 3. Fit Platt Calibrator on OOF predictions
    print("Fitting Platt Scaling calibrator on OOF predictions...")
    calibrator = LogisticRegression(C=1e5, solver="lbfgs", random_state=RANDOM_SEED)
    calibrator.fit(oof_raw_probs.reshape(-1, 1), dev_df[TARGET_COLUMN])
    print(f"Platt Calibrator: w = {calibrator.coef_[0][0]:.4f}, b = {calibrator.intercept_[0]:.4f}")

    # 4. Train final models on full Development pool
    print("\nTraining final models on full Development pool...")
    dev_df_final = dev_df.copy()
    dev_df_final["cohort_percentile"] = compute_cohort_percentile(dev_df, dev_df)

    final_catboost = build_catboost()
    final_catboost.fit(dev_df_final[FEATURE_COLUMNS], dev_df_final[TARGET_COLUMN])

    final_baseline = build_baseline()
    final_baseline.fit(dev_df_final[FEATURE_COLUMNS], dev_df_final[TARGET_COLUMN])

    # 5. Evaluate on locked test set
    print("\nEvaluating on locked test set...")
    test_df_final = test_df.copy()
    test_df_final["cohort_percentile"] = compute_cohort_percentile(dev_df, test_df)

    x_test = test_df_final[FEATURE_COLUMNS]
    y_test = test_df_final[TARGET_COLUMN].to_numpy()

    # Model predictions
    prev_rate = dev_df[TARGET_COLUMN].mean()
    prev_probs = np.full(len(y_test), fill_value=prev_rate)

    lr_probs = final_baseline.predict_proba(x_test)[:, 1]
    cb_raw_probs = final_catboost.predict_proba(x_test)[:, 1]
    cb_cal_probs = calibrator.predict_proba(cb_raw_probs.reshape(-1, 1))[:, 1]

    test_results = {
        "Prevalence Baseline": evaluate(y_test, prev_probs),
        "Logistic regression (baseline)": evaluate(y_test, lr_probs),
        "CatBoost (Uncalibrated)": evaluate(y_test, cb_raw_probs),
        "CatBoost (Calibrated - Platt)": evaluate(y_test, cb_cal_probs),
    }

    # Calibration analysis for Calibrated CatBoost
    cal_bins, ece, mce = compute_calibration_bins(y_test, cb_cal_probs, n_bins=5)

    matrix = confusion_matrix(
        y_test,
        (cb_cal_probs >= DECISION_THRESHOLD).astype(int),
    )

    importances = pd.Series(
        final_catboost.get_feature_importance(),
        index=FEATURE_COLUMNS,
    )

    # 6. Save models and artifacts
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    final_catboost.save_model(str(MODELS_DIR / MODEL_FILE))
    joblib.dump(calibrator, MODELS_DIR / CALIBRATOR_FILE)

    metadata = {
        "model_file": MODEL_FILE,
        "calibrator_file": CALIBRATOR_FILE,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "catboost_version": catboost.__version__,
        "feature_columns": FEATURE_COLUMNS,
        "target": "at_risk: UCI final grade G3 < 10/20 (UCI benchmark cutoff, not Kenyan policy)",
        "decision_threshold": DECISION_THRESHOLD,
        "development_records": len(dev_df),
        "test_records": len(test_df),
        "unique_students_total": data["student_group"].nunique(),
        "unique_students_dev": dev_df["student_group"].nunique(),
        "unique_students_test": test_df["student_group"].nunique(),
        "parameters": CATBOOST_PARAMS,
        "test_metrics": {
            model_name: {k: round(v, 4) for k, v in m.items()}
            for model_name, m in test_results.items()
        },
        "calibration": {
            "method": "Platt scaling (logistic regression on OOF raw probabilities)",
            "calibrator_weight": round(float(calibrator.coef_[0][0]), 4),
            "calibrator_bias": round(float(calibrator.intercept_[0]), 4),
            "expected_calibration_error": round(float(ece), 4),
            "maximum_calibration_error": round(float(mce), 4),
            "bins": cal_bins,
        },
        "feature_importance": {
            k: round(float(v), 2) for k, v in importances.items()
        },
    }

    (MODELS_DIR / METADATA_FILE).write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    plot_evaluation(y_test, cb_cal_probs, cb_raw_probs, lr_probs, prev_probs, importances)
    write_report(
        dev_df, test_df, cv_summary, test_results,
        cal_bins, ece, mce, matrix, importances, calibrator,
    )

    print("\n" + "=" * 60)
    print("INNER CROSS-VALIDATION SUMMARY (DEVELOPMENT POOL):")
    print("=" * 60)
    print(format_metrics_table(cv_summary))

    print("\n" + "=" * 60)
    print("LOCKED TEST SET EVALUATION:")
    print("=" * 60)
    print(format_metrics_table(test_results))

    print("\n" + "=" * 60)
    print("CALIBRATION BINS (CALIBRATED CATBOOST, 5 UNIFORM BINS):")
    print("=" * 60)
    for b in cal_bins:
        print(f"Bin {b['bin']}: Count={b['count']}, MeanPred={b['mean_pred']:.4f}, ObsRate={b['obs_rate']:.4f}, AbsErr={b['abs_error']:.4f}")
    print(f"Expected Calibration Error (ECE): {ece:.4f}")
    print(f"Maximum Calibration Error (MCE):  {mce:.4f}")

    print("\n" + "=" * 60)
    print("CONFUSION MATRIX (CALIBRATED CATBOOST, THRESHOLD 0.5):")
    print("=" * 60)
    print(f"TN: {matrix[0, 0]}, FP: {matrix[0, 1]}")
    print(f"FN: {matrix[1, 0]}, TP: {matrix[1, 1]}")

    print("\n" + "=" * 60)
    print("FEATURE IMPORTANCE:")
    print("=" * 60)
    print(importances.sort_values(ascending=False).round(2))

    print("\nTraining and evaluation finished successfully.")


if __name__ == "__main__":
    main()
