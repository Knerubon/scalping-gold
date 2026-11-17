"""Source wiring assertions, NOT an MQL5 compiler or runtime test."""

import re
from pathlib import Path

from scalping_gold.core import FEATURE_HASH, FEATURES
from scalping_gold.protocol import Response

ROOT = Path(__file__).resolve().parents[1]


def test_feature_order_hash_and_response_field_count():
    source = (ROOT / "mql5/GoldCore.mqh").read_text()
    assert f'#define FEATURE_HASH "{FEATURE_HASH}"' in source
    names = re.search(r"FeatureNames\[FEATURE_COUNT\]=\{([^}]+)", source)[1]
    assert tuple(re.findall(r'"([a-z0-9_]+)"', names)) == FEATURES
    ea = (ROOT / "mql5/ScalpingGold.mq5").read_text()
    assert f"j.Count()!={len(Response.model_fields)}" in ea


def test_entry_defaults_and_demo_guard_wiring():
    source = (ROOT / "mql5/ScalpingGold.mq5").read_text()
    assert "input bool AUTO_TRADING=false;" in source
    assert "ACCOUNT_TRADE_MODE_DEMO" in source
    assert "ACCOUNT_TRADE_MODE_REAL" not in source  # no real-mode enable branch
    for segment in source.split("OrderSend(")[:-1]:
        assert "!Demo()" in segment[-900:], "each trade request has nearby demo recheck"
    assert "ManagePositions(); // independent" in source
    assert "DailyGuard(); // observe floating drawdown" in source
    assert "GlobalVariablesFlush();\n bool sent=OrderSend" in source
