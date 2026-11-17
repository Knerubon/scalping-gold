import hashlib
import json
import time

import numpy as np
import pandas as pd
import pytest

from scalping_gold.core import FEATURE_HASH, FEATURE_VERSION, FEATURES
from scalping_gold.protocol import Request
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
    report = train_models(labels, tmp_path, "synthetic-test", synthetic=True)
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
        now = int(time.time())
        t = now // 300 * 300
        features = dict.fromkeys(FEATURES, 0.0)
        features.update(strategy=1.0, session=float((t // 3600) % 24), planned_rr=2.0)
        manifest = scorer.manifest
        request = Request(
            schema_version="1",
            signal_id=f"XAUUSD-{t}-1-1",
            symbol="XAUUSD",
            strategy_id="trend",
            direction=1,
            closed_bar_utc=t,
            feature_version=FEATURE_VERSION,
            feature_hash=FEATURE_HASH,
            model_version=manifest["model_version"],
            model_hash=manifest["model_hash"],
            timestamp=now,
            expires_at=t + 300,
            features=features,
        )
        response = scorer.score(request, now)
        assert response.decision == "ABSTAIN" and response.reason_code == "model_unapproved"
        assert response.p_win > 0 and response.p_loss > 0
        approval = tmp_path / "approval.json"
        approval.write_text(
            json.dumps(
                {
                    "approved": True,
                    "reviewer": "synthetic-test",
                    "model_hash": manifest["model_hash"],
                    "evaluation_sha256": hashlib.sha256(
                        (tmp_path / "evaluation.json").read_bytes()
                    ).hexdigest(),
                }
            )
        )
        assert not Scorer(tmp_path / kind, approval).approved
        (tmp_path / kind / "model.joblib").write_bytes(b"corrupted")
        assert Scorer(tmp_path / kind).model is None
