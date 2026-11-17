"""Versioned, strict wire contract. UTC seconds are integers, no NaN/coercion."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .core import FEATURE_HASH, FEATURE_VERSION, FEATURES


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @field_validator("direction", mode="before", check_fields=False)
    @classmethod
    def exact_direction(cls, value):
        if type(value) is not int or value not in (-1, 1):
            raise ValueError("direction must be integer +1 or -1")
        return value


class Request(StrictModel):
    schema_version: Literal["1"]
    signal_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    symbol: str = Field(pattern=r"^XAUUSD[A-Za-z0-9_.-]*$")
    strategy_id: Literal["trend", "range", "breakout"]
    direction: Literal[1, -1]
    closed_bar_utc: int = Field(gt=0)
    feature_version: Literal[FEATURE_VERSION]
    feature_hash: Literal[FEATURE_HASH]
    model_version: str = Field(max_length=80, pattern=r"^[A-Za-z0-9_.-]*$")
    model_hash: str = Field(pattern=r"^([a-f0-9]{64})?$")
    timestamp: int = Field(gt=0)
    expires_at: int = Field(gt=0)
    features: dict[str, float]

    @model_validator(mode="after")
    def validate_features(self):
        if set(self.features) != set(FEATURES):
            raise ValueError("feature names/order contract mismatch")
        if not all(math.isfinite(v) for v in self.features.values()):
            raise ValueError("nonfinite feature")
        if (
            self.closed_bar_utc % 300
            or not self.closed_bar_utc
            <= self.timestamp
            < self.expires_at
            <= self.closed_bar_utc + 300
        ):
            raise ValueError("invalid closed-bar availability or expiry")
        expected = f"{self.symbol}-{self.closed_bar_utc}-{dict(trend=1, range=2, breakout=3)[self.strategy_id]}-{self.direction}"
        if self.signal_id != expected:
            raise ValueError("candidate identity mismatch")
        if self.features["strategy"] != dict(trend=1, range=2, breakout=3)[self.strategy_id]:
            raise ValueError("strategy feature mismatch")
        if self.features["session"] != (self.closed_bar_utc // 3600) % 24:
            raise ValueError("session feature mismatch")
        if self.features["planned_rr"] < 1.5 or self.features["spread_atr"] < 0:
            raise ValueError("invalid candidate risk/spread")
        return self


class Response(StrictModel):
    schema_version: Literal["1"]
    signal_id: str
    symbol: str
    strategy_id: Literal["trend", "range", "breakout"]
    direction: Literal[1, -1]
    closed_bar_utc: int
    feature_version: Literal[FEATURE_VERSION]
    feature_hash: Literal[FEATURE_HASH]
    model_version: str
    model_hash: str
    timestamp: int
    expires_at: int
    decision: Literal["APPROVE", "REJECT", "ABSTAIN"]
    p_win: float = Field(ge=0, le=1)
    p_loss: float = Field(ge=0, le=1)
    p_timeout: float = Field(ge=0, le=1)
    estimated_net_r: float = Field(ge=-100, le=100)
    reason_code: str = Field(pattern=r"^[a-z0-9_]+$")

    @model_validator(mode="after")
    def probability_sum(self):
        if abs(self.p_win + self.p_loss + self.p_timeout - 1) > 1e-6:
            raise ValueError("invalid probability normalization")
        return self


def validate_response(response, request, now):
    r = Response.model_validate(response)
    for field in (
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
    ):
        if getattr(r, field) != getattr(request, field):
            raise ValueError(f"response mismatch: {field}")
    if (
        not now - 5 <= r.timestamp <= now + 2
        or not r.timestamp < r.expires_at <= request.expires_at
        or r.expires_at <= now
    ):
        raise ValueError("stale or future response")
    return r
