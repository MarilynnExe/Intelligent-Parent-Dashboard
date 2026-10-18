"""
CatBoost At-Risk Prediction Service (ML-3 Early Warning Pipeline).

This service loads the genuinely trained ML-3 CatBoost model and Platt calibrator.
It produces early-warning academic risk predictions based strictly on Period 1 features:
    1. first_term_pct: Student's first-term academic average (percentage [0, 100])
    2. cohort_percentile: Student's cohort percentile rank (percentage [0, 100])
    3. absences: Attendance records (mapped to benchmark scale)

STRICT PRODUCTION RULES:
    1. EXACT feature order: [first_term_pct, cohort_percentile, absences].
    2. Zero G2 / G3 / demographic leakage.
    3. Raw CatBoost probability is fed through the fitted Platt scaling calibrator.
    4. NEVER fall back to a manual heuristic formula or mock probability.
    5. If model/calibrator is missing or prediction fails, raise ModelServiceError.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import joblib
import numpy as np
from catboost import CatBoostClassifier

logger = logging.getLogger(__name__)

# Base paths to ML-3 trained artifacts
# File location: backend/app/services/catboost_service.py -> parents[3] is project root
BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_PATH = BASE_DIR / "ml_training" / "models" / "catboost_at_risk.cbm"
DEFAULT_CALIBRATOR_PATH = BASE_DIR / "ml_training" / "models" / "probability_calibrator.joblib"
DEFAULT_METADATA_PATH = BASE_DIR / "ml_training" / "models" / "model_metadata.json"

FEATURE_COLUMNS = ["first_term_pct", "cohort_percentile", "absences"]


class ModelServiceError(RuntimeError):
    """Raised when the CatBoost model or calibrator fails to load or infer."""
    pass


def map_period_absences_to_model_feature(
    period_absences: float | int,
    term_index: int = 1,
    total_terms: int = 3,
    annualize: bool = True,
) -> float:
    """
    Transparent mapping between period-to-date absences and benchmark absence horizon.

    Methodological Context (ML-3):
    - Benchmark Training Data (UCI Student Performance): 'absences' was recorded
      as an annual aggregate (mean=4.4, max=75, std=6.2 across 3 terms).
    - Production Setting: Attendance records (status='Absent') are counted period-to-date
      for Term 1 (early warning).
    - In a 3-term academic year (Kenyan CBC/8-4-4 and Portuguese secondary), early Period 1
      observed absences represent approximately 1/3 of the full-year attendance horizon.
    - If annualize=True (default), period absences are scaled by (total_terms / term_index)
      (e.g., period_absences * 3.0 for Term 1) to align with the training distribution's
      annual scale.
    - If annualize=False, raw period absences are used directly, representing a conservative
      estimate that may understate risk as documented in evaluation.md.
    """
    if period_absences is None:
        raise ValueError("Period absences cannot be None.")
    if period_absences < 0:
        raise ValueError(f"Period absences cannot be negative: {period_absences}")

    if annualize:
        scale_factor = float(total_terms) / float(term_index)
        mapped = round(float(period_absences) * scale_factor, 1)
        logger.debug(
            "Mapped period-to-date absences %s to annualized benchmark feature %s (scale: %s)",
            period_absences,
            mapped,
            scale_factor,
        )
        return float(mapped)

    return float(period_absences)


def determine_support_status(calibrated_probability: float) -> str:
    """
    Categorize calibrated support probability into rule-derived status.

    Threshold Rules:
    - probability < 0.35 -> 'On Track'
    - probability < 0.65 -> 'Monitoring Suggested'
    - otherwise          -> 'Targeted Support Recommended'
    """
    if calibrated_probability < 0.35:
        return "On Track"
    elif calibrated_probability < 0.65:
        return "Monitoring Suggested"
    else:
        return "Targeted Support Recommended"


class CatBoostService:
    """
    Production service for CatBoost academic early-warning risk scoring.
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        calibrator_path: str | Path | None = None,
    ):
        self.model_path = Path(
            model_path
            or os.getenv("CATBOOST_MODEL_PATH")
            or DEFAULT_MODEL_PATH
        )
        self.calibrator_path = Path(
            calibrator_path
            or os.getenv("CALIBRATOR_PATH")
            or DEFAULT_CALIBRATOR_PATH
        )

        self._model: CatBoostClassifier | None = None
        self._calibrator: Any = None
        self._load_artifacts()

    def _load_artifacts(self) -> None:
        """
        Loads the CatBoost classifier and Platt calibrator from disk.
        Fails fast and loudly if files are missing or corrupt.
        """
        # 1. Model verification & loading
        if not self.model_path.exists():
            raise ModelServiceError(
                f"CatBoost model file not found at: {self.model_path}. "
                "Ensure ML-3 training pipeline has executed and generated catboost_at_risk.cbm."
            )

        try:
            model = CatBoostClassifier()
            model.load_model(str(self.model_path))
            self._model = model
            logger.info("Successfully loaded CatBoost model from %s", self.model_path)
        except Exception as exc:
            raise ModelServiceError(
                f"Failed to load CatBoost model from {self.model_path}: {exc}"
            ) from exc

        # 2. Calibrator verification & loading
        if not self.calibrator_path.exists():
            raise ModelServiceError(
                f"Probability calibrator file not found at: {self.calibrator_path}. "
                "Ensure ML-3 training pipeline has generated probability_calibrator.joblib."
            )

        try:
            calibrator = joblib.load(str(self.calibrator_path))
            self._calibrator = calibrator
            logger.info("Successfully loaded probability calibrator from %s", self.calibrator_path)
        except Exception as exc:
            raise ModelServiceError(
                f"Failed to load probability calibrator from {self.calibrator_path}: {exc}"
            ) from exc

    @property
    def model(self) -> CatBoostClassifier:
        if self._model is None:
            self._load_artifacts()
        return self._model

    @property
    def calibrator(self) -> Any:
        if self._calibrator is None:
            self._load_artifacts()
        return self._calibrator

    def predict(
        self,
        first_term_pct: float,
        cohort_percentile: float,
        absences: float,
    ) -> Dict[str, Any]:
        """
        Produce calibrated probability of academic risk from Period 1 features.

        Parameters:
        - first_term_pct: Continuous [0, 100]
        - cohort_percentile: Continuous [0, 100]
        - absences: Mapped numeric absence count

        Returns:
        dict with:
            - raw_probability: float in [0, 1]
            - support_probability: float in [0, 1] (calibrated)
            - support_status: "On Track" | "Monitoring Suggested" | "Targeted Support Recommended"
            - features: dictionary of features in exact model order
        """
        # Validate inputs
        if first_term_pct is None or cohort_percentile is None or absences is None:
            raise ModelServiceError(
                f"All three features are required. Received: first_term_pct={first_term_pct}, "
                f"cohort_percentile={cohort_percentile}, absences={absences}"
            )

        try:
            f_first_term = float(first_term_pct)
            f_percentile = float(cohort_percentile)
            f_absences = float(absences)
        except (ValueError, TypeError) as exc:
            raise ModelServiceError(f"Features must be numeric: {exc}") from exc

        # Construct feature vector in exact training order
        feature_vector = np.array([[f_first_term, f_percentile, f_absences]], dtype=np.float64)

        # 1. CatBoost Raw Prediction
        try:
            raw_probs = self.model.predict_proba(feature_vector)
            raw_prob = float(raw_probs[0, 1])
        except Exception as exc:
            raise ModelServiceError(f"CatBoost inference failed: {exc}") from exc

        # 2. Platt Scaling Calibration
        try:
            cal_probs = self.calibrator.predict_proba(np.array([[raw_prob]], dtype=np.float64))
            calibrated_prob = float(cal_probs[0, 1])
        except Exception as exc:
            raise ModelServiceError(f"Probability calibrator inference failed: {exc}") from exc

        # Guarantee range [0.0, 1.0]
        calibrated_prob = float(np.clip(calibrated_prob, 0.0, 1.0))
        raw_prob = float(np.clip(raw_prob, 0.0, 1.0))

        # 3. Rule-derived support status
        status = determine_support_status(calibrated_prob)

        return {
            "raw_probability": round(raw_prob, 4),
            "support_probability": round(calibrated_prob, 4),
            "support_status": status,
            "features": {
                "first_term_pct": f_first_term,
                "cohort_percentile": f_percentile,
                "absences": f_absences,
            },
        }


# Global singleton instance for injection
_instance: CatBoostService | None = None


def get_catboost_service() -> CatBoostService:
    global _instance
    if _instance is None:
        _instance = CatBoostService()
    return _instance
