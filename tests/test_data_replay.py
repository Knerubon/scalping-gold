import numpy as np
import pandas as pd
import pytest

from scalping_gold.core import FEATURES, Candidate
from scalping_gold.data import aggregate, extract, read_bars, snapshots
from scalping_gold.replay import Costs, metrics, portfolio, simulate


@pytest.fixture
def bars():
    rng = np.random.default_rng(17)
    close = 2000 + np.cumsum(rng.normal(0, 0.5, 3600))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {
            "open": op,
            "high": np.maximum(op, close) + 0.3,
            "low": np.minimum(op, close) - 0.3,
            "close": close,
            "spread": 0.1,
        },
        index=pd.date_range("2025-01-01", periods=len(close), freq="5min", tz="UTC", name="time"),
    )


@pytest.mark.parametrize("cutoff", [3300, 3301, 3302])
def test_no_future_leakage(bars, cutoff):
    before = list(snapshots(bars.iloc[:cutoff]))
    mutated = bars.copy()
    mutated.iloc[cutoff:, :4] += 1000
    after = [s for s in snapshots(mutated) if s.time <= before[-1].time]
    assert before == after
    a = list(extract(bars.iloc[:cutoff]))
    b = [c for c in extract(mutated) if c.time <= before[-1].time]
    assert a == b
    for s in before:
        assert s.m15_time <= s.time
        assert 0 <= s.time - s.m15_time < 900


def test_resampling_omits_incomplete(bars):
    df = bars.iloc[:12].drop(bars.index[2])
    assert len(aggregate(df, 60)) == 0
    assert len(aggregate(df, 15)) == 3


def test_csv_validation(tmp_path, bars):
    path = tmp_path / "bars.csv"
    bars.iloc[:20].to_csv(path)
    assert len(read_bars(path)) == 20
    bad = bars.iloc[:20].copy()
    bad.iloc[2, bad.columns.get_loc("spread")] = -1
    bad.to_csv(path)
    with pytest.raises(ValueError):
        read_bars(path)


def fixture_trade(bars, direction=1):
    df = bars.iloc[:40].copy()
    df.loc[:, ["open", "close"]] = 100.0
    df.loc[:, "high"], df.loc[:, "low"] = 101.0, 99.0
    t = int(df.index[20].timestamp())
    c = Candidate(
        f"id{direction}",
        t,
        "trend",
        direction,
        100,
        100 - direction * 2,
        100 + direction * 4,
        dict.fromkeys(FEATURES, 0.0),
    )
    return c, df


@pytest.mark.parametrize("direction", [1, -1])
def test_ambiguous_intrabar_is_stop_first(bars, direction):
    c, df = fixture_trade(bars, direction)
    df.iloc[20, df.columns.get_loc("high")] = 110
    df.iloc[20, df.columns.get_loc("low")] = 90
    r = simulate(c, df, Costs(0.01, 0, 0, 0))
    assert r["outcome"] == "LOSS" and r["reason"] == "sl_ambiguous"
    assert r["net_r"] == pytest.approx(-1)


def test_gap_worse_and_end_of_data(bars):
    c, df = fixture_trade(bars)
    df.iloc[21, df.columns.get_loc("open")] = 95
    df.iloc[21, df.columns.get_loc("low")] = 94
    result = simulate(c, df, Costs(0.01, 0, 0, 0))
    assert result["net_r"] < -1
    assert simulate(c, df.iloc[:21], Costs(0.01, 0, 0, 0)) is None


def test_time_label_and_costs(bars):
    c, df = fixture_trade(bars)
    result = simulate(c, df, Costs(0.01, 0, 0.1, 0.2))
    assert result["outcome"] == "TIMEOUT" and result["reason"] == "time_exit"
    assert result["label_end"] == c.time + 3600 and result["net_r"] < 0


def test_portfolio_limits_and_metrics():
    df = pd.DataFrame(
        {
            "time": np.arange(20) * 600 + 86400,
            "label_end": np.arange(20) * 600 + 86700,
            "net_r": [-1.0] * 20,
        }
    )
    assert len(portfolio(df)) == 3
    df.net_r = 1.0
    assert len(portfolio(df)) == 5
    assert metrics([-1, 2, -3])["max_drawdown_r"] == 3


def test_range_uses_only_bars_closed_at_signal_open(bars):
    higher = aggregate(bars, 15)
    for s in list(snapshots(bars))[-24:]:
        opened = pd.to_datetime(s.time - 300, unit="s", utc=True)
        known = higher[higher.index + pd.Timedelta(minutes=15) <= opened].iloc[-20:]
        assert s.support == known.low.min()
        assert s.resistance == known.high.max()
