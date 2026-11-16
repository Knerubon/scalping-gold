"""UTC M5 OHLC preparation; all joins use availability (close) times.

ATR uses MT5's arithmetic TR average, RSI/ADX use Wilder smoothing. Native
indicator seed/rounding parity must be verified against the terminal export.
"""

import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from .core import RegimeDetector, Snapshot, arbitrate, candidates


def read_bars(path):
    df = pd.read_csv(path)
    required = {"time", "open", "high", "low", "close", "spread"}
    if not required <= set(df):
        raise ValueError(f"CSV requires {sorted(required)}; time is UTC bar-open")
    df["time"] = pd.to_datetime(df.time, utc=True, errors="raise")
    df = df.set_index("time")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("bars must be strictly ordered, unique")
    if (df.index.asi8 // 10**9 % 300 != 0).any():
        raise ValueError("M5 bar opens must align to UTC five-minute boundaries")
    numeric = df[list(required - {"time"})].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or (df.spread < 0).any() or (df.low <= 0).any():
        raise ValueError("nonfinite, nonpositive price or negative spread")
    if (
        (df.high < df[["open", "close", "low"]].max(axis=1))
        | (df.low > df[["open", "close"]].min(axis=1))
    ).any():
        raise ValueError("invalid OHLC")
    return df.astype(float)


def wilder(series, period=14):
    """SMA-seeded Wilder recursion, preserving initial unavailable rows."""
    out = pd.Series(np.nan, index=series.index)
    valid = series.dropna()
    if len(valid) < period:
        return out
    seed = valid.iloc[:period].mean()
    offset = series.index.get_loc(valid.index[period - 1])
    out.iloc[offset] = seed
    for i in range(offset + 1, len(series)):
        seed = (seed * (period - 1) + series.iloc[i]) / period
        out.iloc[i] = seed
    return out


def indicators(df):
    out = df.copy()
    previous = df.close.shift(1)
    tr = pd.concat(
        [df.high - df.low, (df.high - previous).abs(), (df.low - previous).abs()], axis=1
    ).max(axis=1)
    tr.iloc[0] = np.nan
    out["atr"] = tr.rolling(14, min_periods=14).mean()
    out["ema20"] = df.close.ewm(span=20, adjust=False).mean()
    out["ema50"] = df.close.ewm(span=50, adjust=False).mean()
    delta = df.close.diff()
    gain, loss = wilder(delta.clip(lower=0)), wilder(-delta.clip(upper=0))
    out["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    out.loc[(loss == 0) & (gain > 0), "rsi"] = 100
    out.loc[(loss == 0) & (gain == 0), "rsi"] = 50
    up, down = df.high.diff(), -df.low.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    plus.iloc[0] = minus.iloc[0] = np.nan
    smooth_tr = wilder(tr)
    out["plus"] = 100 * wilder(plus) / smooth_tr
    out["minus"] = 100 * wilder(minus) / smooth_tr
    denominator = out.plus + out.minus
    dx = (100 * (out.plus - out.minus).abs() / denominator.replace(0, np.nan)).where(
        denominator != 0, 0
    )
    out["adx"] = wilder(dx)
    return out


def aggregate(df, minutes):
    """Drop incomplete buckets instead of manufacturing available higher bars."""
    grouped = df.resample(f"{minutes}min", closed="left", label="left")
    result = grouped.agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "spread": "last"}
    )
    return result[grouped.close.count() == minutes // 5].dropna()


def snapshots(df):
    m5 = indicators(df)
    m15 = indicators(aggregate(df, 15))
    h1 = indicators(aggregate(df, 60))
    m15["atr_mean"] = m15.atr.shift(1).rolling(50).mean()
    # Known range at signal-bar OPEN, not signal-bar CLOSE.
    ranges = pd.DataFrame(
        {"support": m15.low.rolling(20).min(), "resistance": m15.high.rolling(20).max()},
        index=m15.index + pd.Timedelta(minutes=15),
    )
    m15.index += pd.Timedelta(minutes=15)
    h1.index += pd.Timedelta(hours=1)
    j = k = r = -1
    for i in range(250, len(m5)):
        opened = m5.index[i]
        closed = opened + pd.Timedelta(minutes=5)
        while j + 1 < len(m15) and m15.index[j + 1] <= closed:
            j += 1
        while k + 1 < len(h1) and h1.index[k + 1] <= closed:
            k += 1
        while r + 1 < len(ranges) and ranges.index[r + 1] <= opened:
            r += 1
        if j < 249 or k < 249 or r < 19:
            continue
        if closed - m15.index[j] >= pd.Timedelta(minutes=15) or closed - h1.index[
            k
        ] >= pd.Timedelta(hours=1):
            continue
        a, b, c, bounds = m5.iloc[i], m15.iloc[j], h1.iloc[k], ranges.iloc[r]
        prior = m5.atr.iloc[i - 100 : i]
        s = Snapshot(
            int(closed.timestamp()),
            int(m15.index[j].timestamp()),
            a.open,
            a.high,
            a.low,
            a.close,
            m5.close.iloc[i - 1],
            m5.close.iloc[i - 3],
            a.ema20,
            m5.ema20.iloc[i - 1],
            a.atr,
            a.rsi,
            b.adx,
            b.plus,
            b.minus,
            b.ema20,
            b.ema50,
            b.atr,
            b.atr_mean,
            bounds.support,
            bounds.resistance,
            float((prior <= a.atr).mean()),
            c.ema20,
            c.atr,
            a.spread,
        )
        if s.valid():
            yield s


def extract(df):
    detector = RegimeDetector()
    for s in snapshots(df):
        c = arbitrate(candidates(s, detector.update(s)))
        if c is not None:
            yield c


def export_candidates(df, path):
    with open(path, "w") as f:
        for c in extract(df):
            f.write(json.dumps(asdict(c), allow_nan=False) + "\n")
