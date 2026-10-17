"""Hourly machine-learning cash flow forecasting and chronological evaluation.

Implements TASK RJ-M1-09:
1. Lightweight Random Forest and HistGradientBoosting models for hourly deposits and withdrawals.
2. Strictly causal historical lag, calendar, and rolling features.
3. Native hourly source resolution (no synthetic splitting).
4. Multi-step forecast paths for 1, 3, 6, 15, and 24-hour horizons.
5. Strict prevention of future realized observations during multi-step forecasting.
6. Chronological train/validation/test splits (no shuffling, no future lookahead).
7. Evaluation and comparison against rolling-mean and seasonal-naive baselines.
8. Calculation of MAE, RMSE, and cumulative multi-hour forecast errors.
9. Measurement of maximum cumulative liquidity-shortfall prediction errors.
10. Explicit reporting of model version, training cutoff, test period, sample counts, and metrics.
11. Explicit baseline fallback for untrained or unavailable ML models.
12. Model reuse: trains once, evaluates and infers efficiently across arbitrary hours.
13. Lazy dependency loading: scikit-learn is imported on demand, preserving contract independence.
"""
from __future__ import annotations

import math
import pickle
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator

from .four_tier import (
    ExactDecimal,
    ForecastRiskMetadata,
    FourTierContract,
    HourlyForecastPoint,
    LocalTimestamp,
    Name,
    NonnegativeDecimal,
    OrganizerHourlyObservation,
    PositiveDecimal,
    PositiveInt,
)
from .hourly_forecasting import (
    HourlyCashFlowBucket,
    HourlyForecastConfig,
    HourlyForecastResult,
    _extract_amounts,
    hourly_rolling_mean_forecast,
    hourly_seasonal_naive_forecast,
    validate_hourly_forecast_inputs,
)

SUPPORTED_ML_ALGORITHMS: tuple[str, ...] = ("hist_gradient_boosting", "random_forest")


def _get_timestamp(obs: Any) -> datetime:
    """Safely extract timestamp from OrganizerHourlyObservation or HourlyCashFlowBucket."""
    if hasattr(obs, "timestamp"):
        return obs.timestamp
    if hasattr(obs, "start_at"):
        return obs.start_at
    raise AttributeError(f"no timestamp or start_at found on {type(obs)}")


def _get_sklearn_regressor(algorithm: str, random_state: int = 42) -> Any:
    """Lazy loader for scikit-learn regressors to avoid eager import side effects."""
    try:
        if algorithm in ("hist_gradient_boosting", "hist_gb", "HistGradientBoostingRegressor"):
            from sklearn.ensemble import HistGradientBoostingRegressor
            return HistGradientBoostingRegressor(
                max_iter=100,
                max_depth=8,
                min_samples_leaf=20,
                random_state=random_state,
            )
        elif algorithm in ("random_forest", "rf", "RandomForestRegressor"):
            from sklearn.ensemble import RandomForestRegressor
            return RandomForestRegressor(
                n_estimators=50,
                max_depth=10,
                min_samples_leaf=10,
                random_state=random_state,
                n_jobs=-1,
            )
        else:
            raise ValueError(f"unsupported ML algorithm: {algorithm}; choose from {SUPPORTED_ML_ALGORITHMS}")
    except ImportError as exc:
        raise RuntimeError("scikit-learn is required for ML forecasting models") from exc


# ---------------------------------------------------------------------------
# Feature Extraction for ML Models
# ---------------------------------------------------------------------------

ML_FEATURE_NAMES: tuple[str, ...] = (
    "forecast_step",
    "target_hour",
    "target_day_of_week",
    "target_is_weekend",
    "sin_target_hour",
    "cos_target_hour",
    "sin_target_day",
    "cos_target_day",
    "seasonal_naive_dep_usd",
    "seasonal_naive_wtd_usd",
    "seasonal_naive_weekly_dep_usd",
    "seasonal_naive_weekly_wtd_usd",
    "as_of_dep_usd",
    "as_of_wtd_usd",
    "rolling_mean_3_dep_usd",
    "rolling_mean_3_wtd_usd",
    "rolling_mean_24_dep_usd",
    "rolling_mean_24_wtd_usd",
    "rolling_volatility_24_dep_usd",
    "rolling_volatility_24_wtd_usd",
    "tier1_repo_rate_apy",
    "tier2_bond_yield_pct",
    "tier3_stock_volatility_pct",
    "tier3_stock_index_price",
)


def extract_ml_features_for_step(
    history: Sequence[Any],
    as_of: datetime,
    step_h: int,
    start_at: datetime | None = None,
) -> list[float]:
    """Extract strictly causal features for predicting target hour `as_of + step_h * 1h`.
    
    All cash-flow lags and rolling statistics are calculated strictly using data up to `as_of`.
    Calendar features for the target time are deterministic future astronomical clock values.
    Market quotes are the most recent observed quotes known at `as_of`.
    """
    if start_at is None:
        target_dt = as_of + timedelta(hours=step_h)
    else:
        target_dt = start_at + timedelta(hours=step_h - 1)

    target_hour = target_dt.hour
    target_dow = target_dt.weekday()
    target_is_weekend = 1.0 if target_dow >= 5 else 0.0

    sin_target_hour = math.sin(2.0 * math.pi * target_hour / 24.0)
    cos_target_hour = math.cos(2.0 * math.pi * target_hour / 24.0)
    sin_target_day = math.sin(2.0 * math.pi * target_dow / 7.0)
    cos_target_day = math.cos(2.0 * math.pi * target_dow / 7.0)

    # Historical cash flows available up to as_of
    n = len(history)
    if n == 0:
        return [float(step_h), float(target_hour), float(target_dow), target_is_weekend,
                sin_target_hour, cos_target_hour, sin_target_day, cos_target_day] + [0.0] * 15

    extracted = [_extract_amounts(o) for o in history]
    d_usds = [x[0] for x in extracted]
    w_usds = [x[1] for x in extracted]

    # Seasonal naive for target hour:
    # Target time is as_of + step_h hours.
    # Looking back 24 hours from target time is (as_of + step_h - 24 hours).
    # Since step_h in [1, 24], (step_h - 24) is in [-23, 0], which is <= 0 (in the past <= as_of).
    # In the history array ending at index n - 1 (at as_of), that index is:
    # idx = (n - 1) + (step_h - 24) = n - 25 + step_h.
    idx_sn = n - 25 + step_h
    if 0 <= idx_sn < n:
        sn_dep = d_usds[idx_sn]
        sn_wtd = w_usds[idx_sn]
    else:
        sn_dep = d_usds[-1]
        sn_wtd = w_usds[-1]

    # Weekly seasonal naive (168h prior to target time)
    idx_w168 = n - 169 + step_h
    if 0 <= idx_w168 < n:
        sn_w168_dep = d_usds[idx_w168]
        sn_w168_wtd = w_usds[idx_w168]
    else:
        sn_w168_dep = sn_dep
        sn_w168_wtd = sn_wtd

    # State at as_of (last observation in history)
    as_of_dep = d_usds[-1]
    as_of_wtd = w_usds[-1]

    # Rolling statistics up to as_of
    rm3_dep = sum(d_usds[-3:]) / min(3, n)
    rm3_wtd = sum(w_usds[-3:]) / min(3, n)

    w24 = min(24, n)
    rm24_dep = sum(d_usds[-w24:]) / w24
    rm24_wtd = sum(w_usds[-w24:]) / w24

    if w24 > 1:
        rstd24_dep = math.sqrt(sum((x - rm24_dep) ** 2 for x in d_usds[-w24:]) / (w24 - 1))
        rstd24_wtd = math.sqrt(sum((x - rm24_wtd) ** 2 for x in w_usds[-w24:]) / (w24 - 1))
    else:
        rstd24_dep = 0.0
        rstd24_wtd = 0.0

    # Market observations at as_of if available
    last_obs = history[-1]
    repo_rate = float(getattr(last_obs, "tier1_repo_rate_apy", 4.30))
    bond_yield = float(getattr(last_obs, "tier2_bond_yield_pct", 4.80))
    stock_vol = float(getattr(last_obs, "tier3_stock_volatility_pct", 18.0))
    stock_price = float(getattr(last_obs, "tier3_stock_index_price", 5000.0))

    return [
        float(step_h),
        float(target_hour),
        float(target_dow),
        target_is_weekend,
        sin_target_hour,
        cos_target_hour,
        sin_target_day,
        cos_target_day,
        sn_dep,
        sn_wtd,
        sn_w168_dep,
        sn_w168_wtd,
        as_of_dep,
        as_of_wtd,
        rm3_dep,
        rm3_wtd,
        rm24_dep,
        rm24_wtd,
        rstd24_dep,
        rstd24_wtd,
        repo_rate,
        bond_yield,
        stock_vol,
        stock_price,
    ]


# ---------------------------------------------------------------------------
# Hourly Cash Flow ML Model
# ---------------------------------------------------------------------------

class HourlyCashFlowMLModel:
    """Trained machine-learning model for hourly deposits and withdrawals.
    
    Supports HistGradientBoosting and RandomForest regressors.
    Strictly causal: accepts historical observations, generates multi-step paths
    without lookahead, and provides empirical validation uncertainty.
    """

    def __init__(
        self,
        algorithm: Literal["hist_gradient_boosting", "random_forest"] = "hist_gradient_boosting",
        model_version: str = "hourly-hist-gb-v1",
        random_state: int = 42,
    ):
        self.algorithm = algorithm
        self.model_version = model_version
        self.random_state = random_state
        self.model_deposits: Any = None
        self.model_withdrawals: Any = None
        self.is_fitted: bool = False
        self.training_cutoff: datetime | None = None
        self.train_sample_count: int = 0
        self.validation_residual_std_cents: int = 0
        self.feature_names = ML_FEATURE_NAMES

    def fit(
        self,
        history: Sequence[Any],
        *,
        validation_history: Sequence[Any] | None = None,
        stride: int = 3,
        horizons: Sequence[int] = (1, 3, 6, 15, 24),
    ) -> HourlyCashFlowMLModel:
        """Train models for deposits and withdrawals on historical sequence.
        
        Extracts multi-step training instances across historical timestamps.
        Calibrates residual uncertainty on the validation set if provided.
        """
        n = len(history)
        if n < 24:
            raise ValueError(f"insufficient history for ML training: {n} observations (need at least 24)")

        X_train: list[list[float]] = []
        yd_train: list[float] = []
        yw_train: list[float] = []

        extracted = [_extract_amounts(o) for o in history]
        d_usds = [x[0] for x in extracted]
        w_usds = [x[1] for x in extracted]
        timestamps = [_get_timestamp(o) for o in history]

        # Chronological multi-step sample generation
        max_horizon = max(horizons)
        start_t = 24 if n >= 48 else max(1, n - max_horizon - 1)
        for t in range(start_t, n - max_horizon, stride):
            as_of_t = timestamps[t]
            hist_t = history[:t + 1]
            for h in horizons:
                target_idx = t + h
                if target_idx >= n:
                    continue
                feats = extract_ml_features_for_step(hist_t, as_of_t, h)
                X_train.append(feats)
                yd_train.append(d_usds[target_idx])
                yw_train.append(w_usds[target_idx])

        if not X_train:
            raise ValueError("failed to construct training samples from history")

        # Fit regressors
        self.model_deposits = _get_sklearn_regressor(self.algorithm, self.random_state)
        self.model_withdrawals = _get_sklearn_regressor(self.algorithm, self.random_state)

        self.model_deposits.fit(X_train, yd_train)
        self.model_withdrawals.fit(X_train, yw_train)

        self.is_fitted = True
        self.training_cutoff = timestamps[-1]
        self.train_sample_count = len(X_train)

        # Calibrate residual uncertainty on validation split if supplied
        if validation_history and len(validation_history) >= 24:
            combined_history = tuple(history) + tuple(validation_history)
            val_start_idx = len(history)
            val_n = len(combined_history)
            residuals_net_cents: list[int] = []

            for t_idx in range(val_start_idx, val_n - 24, stride):
                as_of_val = _get_timestamp(combined_history[t_idx])
                hist_val = combined_history[:t_idx + 1]
                for h in (1, 6, 15, 24):
                    if t_idx + h >= val_n:
                        continue
                    feats = extract_ml_features_for_step(hist_val, as_of_val, h)
                    pred_d = max(0.0, float(self.model_deposits.predict([feats])[0]))
                    pred_w = max(0.0, float(self.model_withdrawals.predict([feats])[0]))
                    pred_net = int((Decimal(str(round(pred_d - pred_w, 2))) * 100).to_integral_value())

                    actual_d, actual_w, _, act_d_cents, act_w_cents, act_net_cents = _extract_amounts(
                        combined_history[t_idx + h]
                    )
                    residuals_net_cents.append(act_net_cents - pred_net)

            if len(residuals_net_cents) > 1:
                mean_res = sum(residuals_net_cents) / len(residuals_net_cents)
                var_res = sum((r - mean_res) ** 2 for r in residuals_net_cents) / (len(residuals_net_cents) - 1)
                self.validation_residual_std_cents = max(0, int(round(math.sqrt(var_res))))
            else:
                self.validation_residual_std_cents = 1000000
        else:
            self.validation_residual_std_cents = 1000000

        return self

    def predict_path(
        self,
        history: Sequence[Any],
        as_of: datetime,
        horizon_hours: int,
        start_at: datetime | None = None,
    ) -> tuple[tuple[int, ...], tuple[int, ...], int]:
        """Predict non-negative deposits, withdrawals, and uncertainty buffer for horizon."""
        if not self.is_fitted:
            raise RuntimeError("cannot predict with an unfitted ML model; fit() or load() first")

        if start_at is None:
            if history and getattr(history[-1], "timestamp", getattr(history[-1], "start_at", None)) == as_of:
                start_at = as_of + timedelta(hours=1)
            else:
                start_at = as_of

        feature_batch: list[list[float]] = []
        for h in range(1, horizon_hours + 1):
            feats = extract_ml_features_for_step(history, as_of, h, start_at=start_at)
            feature_batch.append(feats)

        preds_d_raw = self.model_deposits.predict(feature_batch)
        preds_w_raw = self.model_withdrawals.predict(feature_batch)

        pred_deposits_cents: list[int] = []
        pred_withdrawals_cents: list[int] = []

        for d_val, w_val in zip(preds_d_raw, preds_w_raw):
            dep_cents = max(0, int((Decimal(str(round(float(d_val), 2))) * 100).to_integral_value(rounding=ROUND_HALF_UP)))
            wtd_cents = max(0, int((Decimal(str(round(float(w_val), 2))) * 100).to_integral_value(rounding=ROUND_HALF_UP)))
            pred_deposits_cents.append(dep_cents)
            pred_withdrawals_cents.append(wtd_cents)

        return (
            tuple(pred_deposits_cents),
            tuple(pred_withdrawals_cents),
            self.validation_residual_std_cents,
        )

    def to_bytes(self) -> bytes:
        return pickle.dumps({
            "algorithm": self.algorithm,
            "model_version": self.model_version,
            "random_state": self.random_state,
            "model_deposits": self.model_deposits,
            "model_withdrawals": self.model_withdrawals,
            "is_fitted": self.is_fitted,
            "training_cutoff": self.training_cutoff,
            "train_sample_count": self.train_sample_count,
            "validation_residual_std_cents": self.validation_residual_std_cents,
        })

    @classmethod
    def from_bytes(cls, data: bytes) -> HourlyCashFlowMLModel:
        state = pickle.loads(data)
        model = cls(
            algorithm=state["algorithm"],
            model_version=state["model_version"],
            random_state=state["random_state"],
        )
        model.model_deposits = state["model_deposits"]
        model.model_withdrawals = state["model_withdrawals"]
        model.is_fitted = state["is_fitted"]
        model.training_cutoff = state["training_cutoff"]
        model.train_sample_count = state["train_sample_count"]
        model.validation_residual_std_cents = state["validation_residual_std_cents"]
        return model

    def save(self, filepath: Path | str) -> None:
        Path(filepath).write_bytes(self.to_bytes())

    @classmethod
    def load(cls, filepath: Path | str) -> HourlyCashFlowMLModel:
        return cls.from_bytes(Path(filepath).read_bytes())


# ---------------------------------------------------------------------------
# Hourly ML Forecasting Public Interface
# ---------------------------------------------------------------------------

def hourly_ml_forecast(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    ml_model: HourlyCashFlowMLModel | None = None,
    start_at: datetime | None = None,
    model_version: str = "hourly-hist-gb-v1",
    fallback_model: Literal["seasonal_naive", "rolling_mean"] = "seasonal_naive",
) -> HourlyForecastResult:
    """Generate native hourly forecast using trained ML model with safe baseline fallback.
    
    If ml_model is None or untrained, or if history < 24h, automatically falls back
    to the seasonal-naive or rolling-mean baseline while recording fallback provenance.
    """
    validate_hourly_forecast_inputs(history, as_of=as_of, horizon_hours=horizon_hours)

    # Safe fallback if ML model is unavailable or unfitted
    if ml_model is None or not ml_model.is_fitted or len(history) < 24:
        if fallback_model == "seasonal_naive" and len(history) >= 24:
            base_res = hourly_seasonal_naive_forecast(
                history,
                as_of=as_of,
                horizon_hours=horizon_hours,
                start_at=start_at,
                model_version=f"{model_version}-fallback-seasonal-naive",
            )
        else:
            base_res = hourly_rolling_mean_forecast(
                history,
                as_of=as_of,
                horizon_hours=horizon_hours,
                start_at=start_at,
                model_version=f"{model_version}-fallback-rolling-mean",
            )
        metadata = ForecastRiskMetadata(
            model_version=model_version,
            generated_at=as_of,
            training_data_through=_get_timestamp(history[-1]) if history else as_of,
            granularity_hours=1,
            net_flow_target="deposits_minus_withdrawals",
            uncertainty_status="provisional_uncalibrated",
            evaluation_reference=None,
            notes=(
                f"Resolution: 1h; Horizon: {horizon_hours}h",
                "ML model unavailable or unfitted; fell back to baseline",
            ),
        )
        return HourlyForecastResult(
            generated_at=as_of,
            model_version=model_version,
            resolution="1h",
            horizon_hours=horizon_hours,
            points=base_res.points,
            metadata=metadata,
        )

    if start_at is None:
        if history and getattr(history[-1], "timestamp", getattr(history[-1], "start_at", None)) == as_of:
            start_at = as_of + timedelta(hours=1)
        else:
            start_at = as_of
    else:
        if start_at.tzinfo is not None or start_at.minute or start_at.second or start_at.microsecond:
            raise ValueError("start_at must be a naive datetime on hourly boundary")
        if start_at < as_of:
            raise ValueError("forecast cannot start before decision time as_of")

    # Predict via ML model
    pred_deps, pred_wtds, uncertainty_cents = ml_model.predict_path(
        history, as_of, horizon_hours, start_at=start_at
    )

    hour_delta = timedelta(hours=1)
    points = tuple(
        HourlyForecastPoint(
            start_at=start_at + i * hour_delta,
            predicted_deposits_cents=pred_deps[i],
            predicted_withdrawals_cents=pred_wtds[i],
            predicted_net_flow_cents=pred_deps[i] - pred_wtds[i],
            supplied_uncertainty_buffer_cents=uncertainty_cents,
        )
        for i in range(horizon_hours)
    )

    last_ts = _get_timestamp(history[-1]) if history else as_of
    metadata = ForecastRiskMetadata(
        model_version=model_version,
        generated_at=as_of,
        training_data_through=last_ts,
        granularity_hours=1,
        net_flow_target="deposits_minus_withdrawals",
        uncertainty_status="provisional_uncalibrated",
        evaluation_reference=None,
        notes=(
            f"Resolution: 1h; Horizon: {horizon_hours}h",
            f"Model: {ml_model.model_version}; Algorithm: {ml_model.algorithm}",
            f"Training cutoff: {ml_model.training_cutoff}",
        ),
    )

    return HourlyForecastResult(
        generated_at=as_of,
        model_version=model_version,
        resolution="1h",
        horizon_hours=horizon_hours,
        points=points,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Chronological Evaluation Framework
# ---------------------------------------------------------------------------

class HourlyModelEvaluationReport(FourTierContract):
    """Detailed evaluation report comparing an ML model against baseline over out-of-sample test period."""
    model_version: Name
    algorithm: Name
    baseline_model_version: Name
    train_cutoff: LocalTimestamp
    test_start: LocalTimestamp
    test_end: LocalTimestamp
    train_sample_count: PositiveInt
    test_sample_count: PositiveInt
    horizon_hours: PositiveInt
    mae_deposits_usd: NonnegativeDecimal
    mae_withdrawals_usd: NonnegativeDecimal
    mae_net_usd: NonnegativeDecimal
    rmse_net_usd: NonnegativeDecimal
    cumulative_net_mae_usd: NonnegativeDecimal
    peak_shortfall_mae_usd: NonnegativeDecimal
    baseline_mae_net_usd: NonnegativeDecimal
    baseline_rmse_net_usd: NonnegativeDecimal
    baseline_cumulative_net_mae_usd: NonnegativeDecimal
    baseline_peak_shortfall_mae_usd: NonnegativeDecimal
    net_mae_improvement_pct: ExactDecimal
    net_rmse_improvement_pct: ExactDecimal
    cumulative_net_mae_improvement_pct: ExactDecimal
    peak_shortfall_mae_improvement_pct: ExactDecimal
    notes: tuple[Name, ...] = ()


def evaluate_hourly_forecast_models(
    history: Sequence[Any],
    *,
    horizons: Sequence[int] = (1, 3, 6, 15, 24),
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    eval_stride: int = 12,
    algorithms: Sequence[Literal["hist_gradient_boosting", "random_forest"]] = ("hist_gradient_boosting",),
    random_state: int = 42,
) -> tuple[HourlyModelEvaluationReport, ...]:
    """Execute chronological out-of-sample evaluation comparing ML models against baseline.
    
    Splits history into train (train_ratio), validation (val_ratio), and test (remaining).
    Never leaks future observations or shuffles chronological order.
    Calculates MAE, RMSE, cumulative multi-hour net flow errors, and peak shortfall errors.
    """
    n = len(history)
    if n < 72:
        raise ValueError(f"evaluation requires at least 72 observations, got {n}")

    # Chronological partition
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    train_data = history[:train_end]
    val_data = history[train_end:val_end]
    test_data = history[val_end:]

    train_cutoff = _get_timestamp(train_data[-1])
    test_start = _get_timestamp(test_data[0])
    test_end = _get_timestamp(test_data[-1])

    reports: list[HourlyModelEvaluationReport] = []

    for algo in algorithms:
        model_version = f"hourly-{algo.replace('_', '-')}-v1"
        ml_model = HourlyCashFlowMLModel(algorithm=algo, model_version=model_version, random_state=random_state)
        ml_model.fit(train_data, validation_history=val_data, stride=eval_stride, horizons=horizons)

        for H in horizons:
            ml_d_errors: list[float] = []
            ml_w_errors: list[float] = []
            ml_net_errors: list[float] = []
            ml_net_sq_errors: list[float] = []
            ml_cum_errors: list[float] = []
            ml_shortfall_errors: list[float] = []

            base_net_errors: list[float] = []
            base_net_sq_errors: list[float] = []
            base_cum_errors: list[float] = []
            base_shortfall_errors: list[float] = []

            # Step across test period
            test_n = len(test_data)
            sample_count = 0

            for t_offset in range(0, test_n - H, eval_stride):
                # Combined history up to decision time t
                full_t = val_end + t_offset
                current_as_of = _get_timestamp(history[full_t])
                hist_to_t = history[:full_t + 1]

                # Realized path over horizon H
                realized_path = history[full_t + 1:full_t + H + 1]
                if len(realized_path) < H:
                    continue

                act_d_list = [_extract_amounts(o)[0] for o in realized_path]
                act_w_list = [_extract_amounts(o)[1] for o in realized_path]
                act_net_list = [d - w for d, w in zip(act_d_list, act_w_list)]

                # Realized cumulative net and peak shortfall
                act_cum_net = sum(act_net_list)
                cum_drain = 0.0
                peak_drain_act = 0.0
                for w, d in zip(act_w_list, act_d_list):
                    cum_drain += (w - d)
                    if cum_drain > peak_drain_act:
                        peak_drain_act = cum_drain

                # ML Prediction
                pred_d_cents, pred_w_cents, _ = ml_model.predict_path(hist_to_t, current_as_of, H)
                ml_d_list = [c / 100.0 for c in pred_d_cents]
                ml_w_list = [c / 100.0 for c in pred_w_cents]
                ml_net_list = [d - w for d, w in zip(ml_d_list, ml_w_list)]

                ml_cum_net = sum(ml_net_list)
                cum_drain_ml = 0.0
                peak_drain_ml = 0.0
                for w, d in zip(ml_w_list, ml_d_list):
                    cum_drain_ml += (w - d)
                    if cum_drain_ml > peak_drain_ml:
                        peak_drain_ml = cum_drain_ml

                # Baseline Prediction (Seasonal Naive 24h)
                base_res = hourly_seasonal_naive_forecast(hist_to_t, as_of=current_as_of, horizon_hours=H)
                base_d_list = [p.predicted_deposits_cents / 100.0 for p in base_res.points]
                base_w_list = [p.predicted_withdrawals_cents / 100.0 for p in base_res.points]
                base_net_list = [d - w for d, w in zip(base_d_list, base_w_list)]

                base_cum_net = sum(base_net_list)
                cum_drain_base = 0.0
                peak_drain_base = 0.0
                for w, d in zip(base_w_list, base_d_list):
                    cum_drain_base += (w - d)
                    if cum_drain_base > peak_drain_base:
                        peak_drain_base = cum_drain_base

                # Record errors
                for step in range(H):
                    ml_d_errors.append(abs(act_d_list[step] - ml_d_list[step]))
                    ml_w_errors.append(abs(act_w_list[step] - ml_w_list[step]))
                    net_err_ml = act_net_list[step] - ml_net_list[step]
                    ml_net_errors.append(abs(net_err_ml))
                    ml_net_sq_errors.append(net_err_ml ** 2)

                    net_err_base = act_net_list[step] - base_net_list[step]
                    base_net_errors.append(abs(net_err_base))
                    base_net_sq_errors.append(net_err_base ** 2)

                ml_cum_errors.append(abs(act_cum_net - ml_cum_net))
                base_cum_errors.append(abs(act_cum_net - base_cum_net))

                ml_shortfall_errors.append(abs(peak_drain_act - peak_drain_ml))
                base_shortfall_errors.append(abs(peak_drain_act - peak_drain_base))

                sample_count += 1

            if sample_count == 0:
                continue

            mae_d = sum(ml_d_errors) / len(ml_d_errors)
            mae_w = sum(ml_w_errors) / len(ml_w_errors)
            mae_net = sum(ml_net_errors) / len(ml_net_errors)
            rmse_net = math.sqrt(sum(ml_net_sq_errors) / len(ml_net_sq_errors))
            cum_net_mae = sum(ml_cum_errors) / len(ml_cum_errors)
            peak_shortfall_mae = sum(ml_shortfall_errors) / len(ml_shortfall_errors)

            base_mae_net = sum(base_net_errors) / len(base_net_errors)
            base_rmse_net = math.sqrt(sum(base_net_sq_errors) / len(base_net_sq_errors))
            base_cum_net_mae = sum(base_cum_errors) / len(base_cum_errors)
            base_peak_shortfall_mae = sum(base_shortfall_errors) / len(base_shortfall_errors)

            # Improvements (positive = ML had lower error)
            mae_imp = ((base_mae_net - mae_net) / base_mae_net * 100.0) if base_mae_net > 0 else 0.0
            rmse_imp = ((base_rmse_net - rmse_net) / base_rmse_net * 100.0) if base_rmse_net > 0 else 0.0
            cum_imp = ((base_cum_net_mae - cum_net_mae) / base_cum_net_mae * 100.0) if base_cum_net_mae > 0 else 0.0
            shortfall_imp = ((base_peak_shortfall_mae - peak_shortfall_mae) / base_peak_shortfall_mae * 100.0) if base_peak_shortfall_mae > 0 else 0.0

            report = HourlyModelEvaluationReport(
                model_version=model_version,
                algorithm=algo,
                baseline_model_version="hourly-seasonal-naive-v1",
                train_cutoff=train_cutoff,
                test_start=test_start,
                test_end=test_end,
                train_sample_count=ml_model.train_sample_count,
                test_sample_count=sample_count,
                horizon_hours=H,
                mae_deposits_usd=Decimal(str(round(mae_d, 2))),
                mae_withdrawals_usd=Decimal(str(round(mae_w, 2))),
                mae_net_usd=Decimal(str(round(mae_net, 2))),
                rmse_net_usd=Decimal(str(round(rmse_net, 2))),
                cumulative_net_mae_usd=Decimal(str(round(cum_net_mae, 2))),
                peak_shortfall_mae_usd=Decimal(str(round(peak_shortfall_mae, 2))),
                baseline_mae_net_usd=Decimal(str(round(base_mae_net, 2))),
                baseline_rmse_net_usd=Decimal(str(round(base_rmse_net, 2))),
                baseline_cumulative_net_mae_usd=Decimal(str(round(base_cum_net_mae, 2))),
                baseline_peak_shortfall_mae_usd=Decimal(str(round(base_peak_shortfall_mae, 2))),
                net_mae_improvement_pct=Decimal(str(round(mae_imp, 2))),
                net_rmse_improvement_pct=Decimal(str(round(rmse_imp, 2))),
                cumulative_net_mae_improvement_pct=Decimal(str(round(cum_imp, 2))),
                peak_shortfall_mae_improvement_pct=Decimal(str(round(shortfall_imp, 2))),
                notes=(
                    f"Chronological split: train={train_ratio:.0%}, val={val_ratio:.0%}, test={1.0 - train_ratio - val_ratio:.0%}",
                    f"Out-of-sample evaluation on {sample_count} paths of {H} hours each",
                ),
            )
            reports.append(report)

    return tuple(reports)
