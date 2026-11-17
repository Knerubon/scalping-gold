"""Loopback-only inference app. Run using documented uvicorn --host 127.0.0.1.

No model and no separately reviewed OOS approval => ABSTAIN. Never auto-trains.
Joblib must be a trusted local artifact; its hash is checked BEFORE deserialization.
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI

from .core import FEATURE_HASH, FEATURE_VERSION, FEATURES
from .protocol import Request, Response

log = logging.getLogger("scalping_gold")


class Scorer:
    def __init__(self, artifact=None, approval=None):
        self.model = None
        self.manifest = None
        self.approved = False
        self.error = "model_unavailable"
        if artifact is None:
            return
        try:
            root = Path(artifact)
            manifest = json.loads((root / "manifest.json").read_text())
            digest = hashlib.sha256((root / "model.joblib").read_bytes()).hexdigest()
            if (
                manifest["model_hash"] != digest
                or manifest["feature_hash"] != FEATURE_HASH
                or manifest["feature_version"] != FEATURE_VERSION
                or manifest["features"] != list(FEATURES)
            ):
                raise ValueError("artifact_contract_mismatch")
            if not 0 <= manifest["threshold"] <= 1 or set(manifest["class_mean_r"]) != {
                "WIN",
                "LOSS",
                "TIMEOUT",
            }:
                raise ValueError("invalid_model_metadata")
            if not all(np.isfinite(v) and abs(v) <= 100 for v in manifest["class_mean_r"].values()):
                raise ValueError("invalid_class_expectancy")
            for field in ("trained_through", "threshold_through", "evaluation_start"):
                if type(manifest[field]) is not int or manifest[field] <= 0:
                    raise ValueError("invalid_model_horizon")
            if (
                not manifest["trained_through"]
                <= manifest["threshold_through"]
                < manifest["evaluation_start"]
            ):
                raise ValueError("invalid_model_chronology")
            model = joblib.load(root / "model.joblib")
            if set(model.classes_) != {"WIN", "LOSS", "TIMEOUT"} or list(
                model.feature_names_in_
            ) != list(FEATURES):
                raise ValueError("model_class_or_feature_mismatch")
            self.model, self.manifest = model, manifest
            self.error = "model_unapproved"
            if approval:
                evidence = json.loads(Path(approval).read_text())
                report_bytes = (root.parent / "evaluation.json").read_bytes()
                report = json.loads(report_bytes)
                if (
                    evidence.get("approved") is True
                    and evidence.get("model_hash") == digest
                    and evidence.get("evaluation_sha256")
                    == hashlib.sha256(report_bytes).hexdigest()
                    and isinstance(evidence.get("reviewer"), str)
                    and evidence["reviewer"].strip()
                    and report.get("synthetic") is False
                    and report.get("test_start", 0) > manifest["threshold_through"]
                ):
                    self.approved = True
                    self.error = ""
        except Exception:
            # No path, artifact payload or account data exposed in health/error logs.
            log.error(
                json.dumps(
                    {"event": "artifact_load_failed", "reason": "invalid_or_missing_artifact"}
                )
            )
            self.model, self.manifest = None, None
            self.error = "artifact_invalid"

    def score(self, request: Request, now=None):
        now = int(time.time()) if now is None else now
        base = {
            key: getattr(request, key)
            for key in (
                "schema_version",
                "signal_id",
                "symbol",
                "strategy_id",
                "direction",
                "closed_bar_utc",
                "feature_version",
                "feature_hash",
                "model_version",
                "model_hash",
            )
        }
        base.update(
            timestamp=now,
            expires_at=min(now + 5, request.expires_at),
            p_win=0.0,
            p_loss=0.0,
            p_timeout=1.0,
            estimated_net_r=0.0,
            decision="ABSTAIN",
            reason_code=self.error or "internal_error",
        )
        started = time.perf_counter()
        if (
            request.timestamp > now + 2
            or now - request.timestamp > 5
            or request.expires_at <= now
            or request.closed_bar_utc > now
        ):
            base["reason_code"] = "stale_request"
        elif self.model is not None:
            m = self.manifest
            if request.model_version != m["model_version"] or request.model_hash != m["model_hash"]:
                base["reason_code"] = "model_mismatch"
            elif request.closed_bar_utc <= m["threshold_through"]:
                base["reason_code"] = "model_from_future"
            else:
                try:
                    frame = pd.DataFrame(
                        [[request.features[f] for f in FEATURES]], columns=FEATURES
                    )
                    probabilities = self.model.predict_proba(frame)[0]
                    if (
                        not np.isfinite(probabilities).all()
                        or (probabilities < 0).any()
                        or abs(probabilities.sum() - 1) > 1e-6
                    ):
                        raise ValueError("invalid_probabilities")
                    p = dict(zip(self.model.classes_, map(float, probabilities), strict=True))
                    expected = sum(p[c] * m["class_mean_r"][c] for c in p)
                    base.update(
                        p_win=p["WIN"],
                        p_loss=p["LOSS"],
                        p_timeout=p["TIMEOUT"],
                        estimated_net_r=expected,
                    )
                    if not self.approved:
                        base["reason_code"] = "model_unapproved"
                    else:
                        allow = p["WIN"] >= m["threshold"] and expected > 0
                        base.update(
                            decision="APPROVE" if allow else "REJECT",
                            reason_code="threshold_pass" if allow else "threshold_reject",
                        )
                except Exception:
                    base.update(
                        decision="ABSTAIN",
                        reason_code="prediction_error",
                        p_win=0.0,
                        p_loss=0.0,
                        p_timeout=1.0,
                        estimated_net_r=0.0,
                    )
        latency = time.perf_counter() - started
        if latency > 2:
            base.update(decision="ABSTAIN", reason_code="inference_timeout")
        log.info(
            json.dumps(
                {
                    "event": "score",
                    "signal_id": request.signal_id,
                    "decision": base["decision"],
                    "reason": base["reason_code"],
                    "p_win": base["p_win"],
                    "p_loss": base["p_loss"],
                    "p_timeout": base["p_timeout"],
                    "estimated_net_r": base["estimated_net_r"],
                    "model_version": request.model_version,
                    "latency_ms": round(latency * 1000, 3),
                }
            )
        )
        return Response(**base)


def create_app(scorer=None):
    scorer = scorer or Scorer(os.getenv("SG_ARTIFACT"), os.getenv("SG_APPROVAL"))
    app = FastAPI(title="Scalping Gold V1 local inference", version="1")

    @app.get("/health")
    def health():
        return {
            "status": "ready" if scorer.approved else "shadow_or_unavailable",
            "model_loaded": scorer.model is not None,
            "approved": scorer.approved,
            "feature_version": FEATURE_VERSION,
            "feature_hash": FEATURE_HASH,
        }

    @app.post("/score", response_model=Response)
    def score(request: Request):
        return scorer.score(request)

    return app


app = create_app()
