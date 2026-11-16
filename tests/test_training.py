import json

import numpy as np
import pandas as pd
import pytest

from scalping_gold.core import FEATURES
from scalping_gold.service import Scorer
from scalping_gold.train import purged_split, train_models, validate_dataset


@pytest.fixture
def labels():
    rng = np.random.default_rng(42)
    n = 360
    df = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=FEATURES)
    df["signal_id"] = [f"synthetic-{i}" for i in range(n)]
    df["time"] = 1700000000 + np.arange(n) * 7200
    df["label_end"] = df.time + 3600
    df["outcome"] = np.array(["LOSS", "TIMEOUT", "WIN"])[np.arange(n) % 3]
    df["net_r"] = np.tile([-1.0, -0.1, 2.0], n // 3)
    return df


def test_purge_and_embargo(labels):
    parts = purged_split(labels)
    for a, b in zip(parts, parts[1:]):
        assert a.label_end.max() < b.time.min()
    bad = labels.copy()
    bad.iloc[1, bad.columns.get_loc("signal_id")] = bad.signal_id.iloc[0]
    with pytest.raises(ValueError):
        validate_dataset(bad)


def test_both_models_calibration_walkforward_and_hash(tmp_path, labels):
    report = train_models(labels, tmp_path, "synthetic-test")
    # Explicitly mark synthetic reports; never eligible for approval.
    report["synthetic"] = True
    (tmp_path / "evaluation.json").write_text(json.dumps(report))
    assert set(report["models"]) == {"logistic", "lightgbm"}
    for kind in report["models"]:
        result = report["models"][kind]
        assert np.isfinite(result["calibration"]["log_loss"])
        assert len(result["walk_forward"]) == 3
        scorer = Scorer(tmp_path / kind)
        assert scorer.model is not None and not scorer.approved
        (tmp_path / kind / "model.joblib").write_bytes(b"corrupted")
        assert Scorer(tmp_path / kind).model is None
