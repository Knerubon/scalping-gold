"""Purged time validation with frozen held-out sigmoid calibration.

Training consumes candidate labels from replay; no online learning. Artifacts
are NEVER automatically approved. Test reports are untouched by threshold fit.
"""

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .core import FEATURE_HASH, FEATURE_VERSION, FEATURES
from .replay import metrics, portfolio

CLASSES = ("LOSS", "TIMEOUT", "WIN")


def validate_dataset(df):
    required = set(FEATURES) | {"time", "label_end", "net_r", "outcome", "signal_id"}
    if not required <= set(df):
        raise ValueError(f"missing columns {required - set(df)}")
    if not df.time.is_monotonic_increasing or df.signal_id.duplicated().any():
        raise ValueError("dataset must be ordered with unique signals")
    if not np.isfinite(df[list(FEATURES) + ["time", "label_end", "net_r"]].to_numpy(float)).all():
        raise ValueError("nonfinite training data")
    if (df.label_end <= df.time).any() or (df.label_end > df.time + 5400).any():
        raise ValueError("invalid label horizon")
    if not set(df.outcome) <= set(CLASSES):
        raise ValueError("unknown outcome")


def purged_split(df, fractions=(0.5, 0.65, 0.8), embargo=300):
    """Four chronological partitions: fit, calibration, threshold, test.

    Remove every earlier label intersecting next partition; leave an additional
    embargo after each boundary. Same timestamps never enter separate partitions.
    """
    times = np.sort(df.time.unique())
    if len(times) < 20:
        raise ValueError("insufficient chronological observations")
    boundaries = [times[min(int(len(times) * f), len(times) - 1)] for f in fractions]
    groups = []
    lower = -np.inf
    for boundary in boundaries:
        groups.append(df[(df.time >= lower) & (df.label_end < boundary)])
        lower = boundary + embargo
    groups.append(df[df.time >= lower])
    if any(len(g) < 3 for g in groups):
        raise ValueError("insufficient data after horizon purge and embargo")
    return groups


def estimator(kind):
    if kind == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1500, random_state=17))
    if kind == "lightgbm":
        return LGBMClassifier(
            n_estimators=100,
            num_leaves=7,
            max_depth=3,
            learning_rate=0.03,
            min_child_samples=20,
            random_state=17,
            n_jobs=1,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
        )
    raise ValueError("unknown model")


def fit_calibrated(train, calibration, kind):
    if set(train.outcome) != set(CLASSES) or set(calibration.outcome) != set(CLASSES):
        raise ValueError("all three outcome classes required in fit and calibration windows")
    base = estimator(kind)
    base.fit(train[list(FEATURES)], train.outcome)
    calibrated = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid")
    calibrated.fit(calibration[list(FEATURES)], calibration.outcome)
    return calibrated


def predictions(model, df, means):
    probabilities = model.predict_proba(df[list(FEATURES)])
    win = probabilities[:, list(model.classes_).index("WIN")]
    expected = sum(probabilities[:, i] * means[label] for i, label in enumerate(model.classes_))
    return probabilities, win, expected


def calibration_report(model, df, probabilities):
    classes = list(model.classes_)
    truth = np.column_stack([(df.outcome == c).to_numpy(float) for c in classes])
    confidence = probabilities.max(axis=1)
    correct = (np.asarray(classes)[probabilities.argmax(axis=1)] == df.outcome.to_numpy()).astype(
        float
    )
    ece = 0.0
    bins = []
    for low in np.linspace(0, 0.9, 10):
        mask = (confidence >= low) & (confidence < low + 0.1 + 1e-12)
        if mask.any():
            gap = abs(float(correct[mask].mean() - confidence[mask].mean()))
            ece += float(mask.mean()) * gap
            bins.append({"lower": float(low), "count": int(mask.sum()), "gap": gap})
    return {
        "log_loss": float(log_loss(df.outcome, probabilities, labels=classes)),
        "multiclass_brier": float(np.mean(np.sum((truth - probabilities) ** 2, axis=1))),
        "ece": ece,
        "reliability_bins": bins,
    }


def choose_threshold(model, validation, means):
    _, pwin, expected = predictions(model, validation, means)
    trials = []
    for threshold in np.arange(0.4, 0.851, 0.05):
        keep = pd.Series((pwin >= threshold) & (expected > 0), index=validation.index)
        result = metrics(portfolio(validation, keep).net_r)
        # Avoid selecting a threshold based on one lucky trade.
        score = result["net_expectancy_r"] if result["trades"] >= 10 else -np.inf
        trials.append((score, float(threshold)))
    best = max(trials)
    return best[1] if np.isfinite(best[0]) else 1.0


def walk_forward(df, kind, folds=3):
    reports = []
    for fraction in np.linspace(0.6, 1.0, folds):
        subset = df.iloc[: int(len(df) * fraction)]
        try:
            train, cal, validation, test = purged_split(subset)
            model = fit_calibrated(train, cal, kind)
            means = train.groupby("outcome").net_r.mean().to_dict()
            threshold = choose_threshold(model, validation, means)
            p, win, expected = predictions(model, test, means)
            keep = pd.Series((win >= threshold) & (expected > 0), index=test.index)
            reports.append(
                {
                    "fit_end": int(train.label_end.max()),
                    "test_start": int(test.time.min()),
                    "test_end": int(test.label_end.max()),
                    "threshold": threshold,
                    **metrics(portfolio(test, keep).net_r),
                    "calibration": calibration_report(model, test, p),
                }
            )
        except ValueError as error:
            reports.append({"status": "insufficient_data", "reason": str(error)})
    return reports


def train_models(df, output, version="research-v1", synthetic=False):
    validate_dataset(df)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    train, cal, validation, test = purged_split(df)
    report = {
        "synthetic": synthetic,
        "approval": "unapproved",
        "feature_hash": FEATURE_HASH,
        "candidate_count": len(df),
        "dataset_sha256": hashlib.sha256(df.to_csv(index=False).encode()).hexdigest(),
        "partitions": [len(g) for g in (train, cal, validation, test)],
        "test_start": int(test.time.min()),
        "baseline": metrics(portfolio(test).net_r),
        "models": {},
    }
    for kind in ("logistic", "lightgbm"):
        model = fit_calibrated(train, cal, kind)
        means = train.groupby("outcome").net_r.mean().to_dict()
        threshold = choose_threshold(model, validation, means)
        probabilities, win, expected = predictions(model, test, means)
        keep = pd.Series((win >= threshold) & (expected > 0), index=test.index)
        report["models"][kind] = {
            **metrics(portfolio(test, keep).net_r),
            "threshold": threshold,
            "rejection_rate": float(1 - keep.mean()),
            "calibration": calibration_report(model, test, probabilities),
            "walk_forward": walk_forward(df, kind),
        }
        target = output / kind
        target.mkdir(exist_ok=True)
        joblib.dump(model, target / "model.joblib")
        digest = hashlib.sha256((target / "model.joblib").read_bytes()).hexdigest()
        manifest = {
            "model_version": version + "-" + kind,
            "model_hash": digest,
            "feature_version": FEATURE_VERSION,
            "feature_hash": FEATURE_HASH,
            "features": list(FEATURES),
            "threshold": threshold,
            "class_mean_r": means,
            "approved": False,
            "trained_through": int(cal.label_end.max()),
            "threshold_through": int(validation.label_end.max()),
            "evaluation_start": int(test.time.min()),
        }
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False))
        # Only untouched test decisions are eligible for offline replay.
        scored = test[["signal_id", "time"]].copy()
        scored["p_win"], scored["expected_r"] = win, expected
        for index, label in enumerate(model.classes_):
            scored["p_" + label.lower()] = probabilities[:, index]
        scored.to_csv(target / "test-scores.csv", index=False)
    (output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("labels")
    parser.add_argument("--output", default="artifacts")
    parser.add_argument("--version", default="research-v1")
    parser.add_argument(
        "--synthetic", action="store_true", help="mark non-market data ineligible for approval"
    )
    args = parser.parse_args()
    train_models(pd.read_csv(args.labels), args.output, args.version, args.synthetic)


if __name__ == "__main__":
    main()
