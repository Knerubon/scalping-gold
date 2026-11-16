"""Conservative OHLC outcome labeling and identical-data evaluation.

Bid OHLC with spread in price units. Adverse SL gaps use the open; profitable
TP gaps receive only target. If both levels touch, SL wins. Updated stops become
active on the following bar. Tick-level modeling remains required in MT5.
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import Position
from .data import indicators


@dataclass(frozen=True)
class Costs:
    tick_size: float = 0.01
    slippage_price: float = 0.05
    commission_price: float = 0.10  # complete round-trip cost converted to price
    be_allowance_price: float = 0.20

    def __post_init__(self):
        if (
            self.tick_size <= 0
            or min(self.slippage_price, self.commission_price, self.be_allowance_price) < 0
        ):
            raise ValueError("invalid execution costs")


def simulate(candidate, bars, costs=Costs(), mode="hybrid", prepared=False):
    if mode not in ("fixed", "be", "trailing", "hybrid"):
        raise ValueError("unknown exit mode")
    df = bars if prepared else indicators(bars)
    future = df[df.index >= pd.to_datetime(candidate.time, unit="s", utc=True)]
    # Fixed/BE/trailing also censor at 90 minutes for comparable label horizons;
    # this is dataset censoring, not an asserted EA time exit.
    end = candidate.time + (90 if candidate.strategy == "breakout" else 60) * 60
    future = future[future.index < pd.to_datetime(end, unit="s", utc=True)]
    if future.empty or int(future.index[0].timestamp()) != candidate.time:
        return None
    d = candidate.direction
    first = future.iloc[0]
    entry = first.open + (first.spread if d == 1 else 0) + d * costs.slippage_price
    atr = df.loc[df.index < future.index[0], "atr"].iloc[-1]
    if not np.isfinite(atr) or abs(entry - candidate.entry) > 0.5 * atr:
        return None
    if candidate.strategy == "breakout":
        # Feature distance is measured from signal close; recover the same bound.
        close = candidate.entry - (candidate.features["spread_atr"] * atr if d == 1 else 0)
        boundary = close - d * candidate.features["breakout_distance"] * atr
        if d * (entry - boundary) > 0.5 * atr:
            return None
    sl = (
        math.floor(candidate.sl / costs.tick_size)
        if d == 1
        else math.ceil(candidate.sl / costs.tick_size)
    ) * costs.tick_size
    r = d * (entry - sl)
    if r <= 0:
        return None
    tp = (
        candidate.tp
        if candidate.strategy == "range"
        else entry + d * r * (2.5 if candidate.strategy == "breakout" else 2)
    )
    tp = (
        math.floor(tp / costs.tick_size) if d == 1 else math.ceil(tp / costs.tick_size)
    ) * costs.tick_size
    if d * (tp - entry) / r < 1.5:
        return None
    p = Position(candidate.signal_id, candidate.strategy, d, entry, r, sl, tp, candidate.time)
    exit_price = None
    outcome = "TIMEOUT"
    reason = "censored"
    finish = None
    for opened, bar in future.iterrows():
        # exit price side: bid for long, ask for short
        spread = bar.spread if d == -1 else 0
        low, high, opening = bar.low + spread, bar.high + spread, bar.open + spread
        hit_sl = low <= p.sl if d == 1 else high >= p.sl
        hit_tp = high >= p.tp if d == 1 else low <= p.tp
        if hit_sl:
            exit_price = min(p.sl, opening) if d == 1 else max(p.sl, opening)
            exit_price -= d * costs.slippage_price
            reason = "sl_ambiguous" if hit_tp else "sl"
        elif hit_tp:
            exit_price, reason = p.tp, "tp"
        finish = int(opened.timestamp()) + 300
        if exit_price is not None:
            outcome = "WIN" if d * (exit_price - entry) - costs.commission_price > 0 else "LOSS"
            break
        # ATR from bar that just closed is available for NEXT bar only.
        action, _ = p.manage(
            bar.close,
            bar.close + bar.spread,
            bar.atr,
            finish,
            costs.tick_size,
            costs.be_allowance_price,
            mode,
        )
        if action == "CLOSE":
            exit_price = bar.close + (bar.spread if d == -1 else 0) - d * costs.slippage_price
            reason = "time_exit"
            break
    if exit_price is None:
        last = future.iloc[-1]
        if finish < end:
            return None  # no invented end-of-data/gap timeout labels
        exit_price = last.close + (last.spread if d == -1 else 0) - d * costs.slippage_price
    net_r = (d * (exit_price - entry) - costs.commission_price) / r
    return {
        "signal_id": candidate.signal_id,
        "time": candidate.time,
        "label_end": finish,
        "strategy": candidate.strategy,
        "direction": d,
        "net_r": net_r,
        "outcome": outcome,
        "reason": reason,
        **candidate.features,
    }


def label_candidates(candidates, bars, costs=Costs(), mode="hybrid"):
    prepared = indicators(bars)
    return pd.DataFrame(
        [
            r
            for c in candidates
            if (r := simulate(c, prepared, costs, mode, prepared=True)) is not None
        ]
    )


def metrics(net_r):
    r = np.asarray(net_r, dtype=float)
    if not len(r):
        return {"trades": 0, "net_expectancy_r": None, "profit_factor": None, "max_drawdown_r": 0.0}
    cumulative = np.r_[0, np.cumsum(r)]
    dd = np.maximum.accumulate(cumulative) - cumulative
    losses = -r[r < 0].sum()
    return {
        "trades": len(r),
        "net_expectancy_r": float(r.mean()),
        "profit_factor": float(r[r > 0].sum() / losses) if losses else None,
        "max_drawdown_r": float(dd.max()),
    }


def portfolio(rows, keep=None):
    """One open symbol position, 5/day, three losses and 2% daily drawdown lock.

    Uses fixed 0.5% risk and normalized starting equity=1; compares model gates
    using the same candidate/cost stream. No risk sizing based on future outcomes.
    """
    if rows.empty:
        return rows
    selected, busy_until, day, count, losses, locked = [], -1, None, 0, 0, False
    equity, baseline = 1.0, 1.0
    for idx, row in rows.sort_values("time").iterrows():
        if row.time < busy_until:
            continue
        this_day = int(row.server_day) if "server_day" in rows else int(row.time) // 86400
        if this_day != day:
            day, count, losses, locked, baseline = this_day, 0, 0, False, equity
        if (
            row.time < busy_until
            or locked
            or count >= 5
            or (keep is not None and not keep.loc[idx])
        ):
            continue
        selected.append(idx)
        busy_until = row.label_end
        equity += equity * 0.005 * row.net_r
        count += 1
        losses = losses + 1 if row.net_r < 0 else 0
        locked = losses >= 3 or equity <= baseline * 0.98
    return rows.loc[selected]
