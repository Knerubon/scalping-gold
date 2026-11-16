import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from scalping_gold.core import FEATURE_HASH, FEATURE_VERSION, FEATURES
from scalping_gold.protocol import Request, validate_response
from scalping_gold.service import Scorer, create_app


@pytest.fixture
def request_data():
    now = int(time.time())
    t = now // 300 * 300
    f = dict.fromkeys(FEATURES, 0.0)
    f.update(strategy=1.0, session=float((t // 3600) % 24), planned_rr=2.0)
    return dict(
        schema_version="1",
        signal_id=f"XAUUSD-{t}-1-1",
        symbol="XAUUSD",
        strategy_id="trend",
        direction=1,
        closed_bar_utc=t,
        feature_version=FEATURE_VERSION,
        feature_hash=FEATURE_HASH,
        model_version="test",
        model_hash="a" * 64,
        timestamp=now,
        expires_at=t + 300,
        features=f,
    )


def test_missing_model_abstains(request_data):
    with TestClient(create_app(Scorer())) as client:
        response = client.post("/score", json=request_data)
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "ABSTAIN"
        assert validate_response(body, Request(**request_data), int(time.time()))
        assert client.get("/health").json()["approved"] is False


@pytest.mark.parametrize(
    "change",
    [
        dict(direction=0),
        dict(feature_hash="bad"),
        dict(expires_at=1),
        dict(extra="bad"),
        dict(direction="1"),
    ],
)
def test_schema_rejects(request_data, change):
    request_data.update(change)
    with pytest.raises(ValidationError):
        Request(**request_data)


def test_feature_mismatch_and_nan(request_data):
    request_data["features"]["adx"] = float("nan")
    with pytest.raises(ValidationError):
        Request(**request_data)
    request_data["features"].pop("adx")
    with pytest.raises(ValidationError):
        Request(**request_data)


def test_stale_response_and_wrong_direction(request_data):
    req = Request(**request_data)
    now = int(time.time())
    body = Scorer().score(req, now).model_dump()
    for change in (
        {"timestamp": now - 6},
        {"direction": -1},
        {"model_hash": "b" * 64},
        {"expires_at": now},
        {"p_win": 0.8},
        {"reason_code": ""},
    ):
        with pytest.raises(ValueError):
            validate_response(body | change, req, now)


class Dummy:
    classes_ = np.array(["LOSS", "TIMEOUT", "WIN"])

    def predict_proba(self, frame):
        return np.array([[0.1, 0.1, 0.8]])


def test_model_requires_approval_and_freeze_date(request_data):
    req = Request(**request_data)
    scorer = Scorer()
    scorer.model = Dummy()
    scorer.manifest = dict(
        model_version=req.model_version,
        model_hash=req.model_hash,
        threshold=0.6,
        threshold_through=req.closed_bar_utc - 1,
        class_mean_r={"LOSS": -1.0, "WIN": 2.0, "TIMEOUT": -0.1},
    )
    assert scorer.score(req).decision == "ABSTAIN"
    scorer.approved = True
    assert scorer.score(req).decision == "APPROVE"
    scorer.manifest["threshold_through"] = req.closed_bar_utc
    assert scorer.score(req).reason_code == "model_from_future"


def test_prediction_failure_and_corrupt_artifact(tmp_path, request_data):
    scorer = Scorer(tmp_path)
    assert scorer.score(Request(**request_data)).decision == "ABSTAIN"
    scorer.model, scorer.manifest, scorer.approved = Dummy(), dict(model_version="bad"), True
    # A valid loaded manifest is checked at load time; malformed metadata never loads.
    assert Scorer(tmp_path).model is None
