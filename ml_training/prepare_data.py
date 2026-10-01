"""
Prepare the UCI Student Performance dataset for CatBoost training.

Only features that the Intelligent Parent Dashboard can compute from its own
database are kept, so the trained model can be used on real students:

    first_term_pct    <- Assessment.percentage (first assessment period)
    latest_term_pct   <- Assessment.percentage (most recent assessment period)
    grade_trend       <- latest_term_pct - first_term_pct
    cohort_percentile <- CohortPercentile.percentile_rank
    absences          <- count of Attendance records with status "Absent"

Target:
    at_risk = 1 when the final grade (G3) is below 10 out of 20 (a fail).

Source: Cortez & Silva (2008), UCI Machine Learning Repository, CC BY 4.0.
"""

from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

MAX_GRADE = 20
PASS_MARK = 10

# Columns the dataset authors use to identify the same student across
# the mathematics and Portuguese files (see student-merge.R).
STUDENT_IDENTITY_COLUMNS = [
    "school", "sex", "age", "address", "famsize", "Pstatus",
    "Medu", "Fedu", "Mjob", "Fjob", "reason", "nursery", "internet"
]

FEATURE_COLUMNS = [
    "first_term_pct",
    "latest_term_pct",
    "grade_trend",
    "cohort_percentile",
    "absences"
]

TARGET_COLUMN = "at_risk"


def cohort_percentile(scores: pd.Series) -> pd.Series:
    """
    Percentile rank using the same formula as PercentileService:
    (number below + 0.5 * number equal) / cohort size * 100
    """
    values = scores.to_numpy()
    n = len(values)

    return scores.apply(
        lambda score: round(
            ((values < score).sum() + 0.5 * (values == score).sum())
            / n * 100,
            1
        )
    )


def load_raw_data() -> pd.DataFrame:
    maths = pd.read_csv(RAW_DIR / "student-mat.csv", sep=";")
    maths["subject"] = "Mathematics"

    portuguese = pd.read_csv(RAW_DIR / "student-por.csv", sep=";")
    portuguese["subject"] = "Portuguese"

    return pd.concat([maths, portuguese], ignore_index=True)


def build_features(raw: pd.DataFrame) -> pd.DataFrame:
    data = pd.DataFrame()

    data["first_term_pct"] = raw["G1"] / MAX_GRADE * 100
    data["latest_term_pct"] = raw["G2"] / MAX_GRADE * 100
    data["grade_trend"] = data["latest_term_pct"] - data["first_term_pct"]

    # Cohort = same school and subject, ranked on the average of the
    # assessments available before the final exam.
    average_pct = (data["first_term_pct"] + data["latest_term_pct"]) / 2
    cohort_keys = [raw["school"], raw["subject"]]
    data["cohort_percentile"] = (
        average_pct.groupby(cohort_keys).transform(cohort_percentile)
    )

    data["absences"] = raw["absences"]

    data[TARGET_COLUMN] = (raw["G3"] < PASS_MARK).astype(int)

    # Used only to keep the same student out of both train and test sets.
    data["student_group"] = (
        raw[STUDENT_IDENTITY_COLUMNS]
        .astype(str)
        .agg("|".join, axis=1)
        .factorize()[0]
    )

    data["subject"] = raw["subject"]
    data["school"] = raw["school"]

    return data


def main():
    raw = load_raw_data()
    data = build_features(raw)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "training_data.csv"
    data.to_csv(output_path, index=False)

    print(f"Records:          {len(data)}")
    print(f"Unique students:  {data['student_group'].nunique()}")
    print(f"At-risk rate:     {data[TARGET_COLUMN].mean():.1%}")
    print(f"Saved to:         {output_path.relative_to(BASE_DIR)}")
    print()
    print(data[FEATURE_COLUMNS + [TARGET_COLUMN]].describe().round(1))


if __name__ == "__main__":
    main()
