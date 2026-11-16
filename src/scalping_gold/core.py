"""Deterministic closed-bar reference. Prices and costs are in price units."""
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import math

FEATURES = ("ema_distance", "ema_slope", "adx", "di_delta", "rsi", "body_ratio",
            "return_1", "return_3", "atr_percentile", "support_distance",
            "resistance_distance", "range_width", "compression", "breakout_distance",
            "spread_atr", "planned_rr", "session", "strategy", "regime", "h1_distance")
FEATURE_VERSION = "sg-v1"
FEATURE_HASH = sha256(",".join(FEATURES).encode()).hexdigest()
STRATEGIES = {"trend": 1, "range": 2, "breakout": 3}
REGIMES = {"WAIT": 0, "TREND_UP": 1, "TREND_DOWN": 2, "RANGE": 3, "BREAKOUT": 4}

@dataclass(frozen=True)
class Snapshot:
    time: int
    m15_time: int
    open: float
    high: float
    low: float
    close: float
    previous_close: float
    close_3: float
    ema: float
    ema_previous: float
    atr: float
    rsi: float
    adx: float
    plus_di: float
    minus_di: float
    ema20: float
    ema50: float
    atr15: float
    atr15_mean: float
    support: float
    resistance: float
    atr_percentile: float
    h1_ema: float
    h1_atr: float
    spread: float = 0.0

    def valid(self):
        return (all(math.isfinite(v) for v in asdict(self).values()) and
                min(self.atr, self.atr15, self.atr15_mean, self.h1_atr) > 0 and
                self.high >= max(self.open, self.close, self.low) and
                self.low <= min(self.open, self.close) and self.close_3 > 0 and
                self.previous_close > 0 and self.resistance > self.support and self.spread >= 0)


def raw_regime(s):
    if not s.valid():
        return "WAIT"
    if s.adx >= 25:
        if s.ema20 > s.ema50 and s.plus_di > s.minus_di:
            return "TREND_UP"
        if s.ema20 < s.ema50 and s.plus_di < s.minus_di:
            return "TREND_DOWN"
        return "WAIT"
    if s.adx < 20 and s.resistance-s.support >= 3*s.atr15:
        return "BREAKOUT" if s.atr15 <= .8*s.atr15_mean else "RANGE"
    return "WAIT"

class RegimeDetector:
    def __init__(self):
        self.current = self.pending = "WAIT"
        self.count = 0
        self.last_time = None

    def update(self, s):
        proposed = raw_regime(s)
        if proposed == "WAIT":
            self.current = self.pending = "WAIT"
            self.count = 0
            self.last_time = s.m15_time
            return self.current
        if s.m15_time != self.last_time:
            self.count = self.count+1 if proposed == self.pending else 1
            self.pending, self.last_time = proposed, s.m15_time
            if self.count >= 2:
                self.current = proposed
        return self.current if self.current == proposed else "WAIT"

@dataclass(frozen=True)
class Candidate:
    signal_id: str
    time: int
    strategy: str
    direction: int
    entry: float
    sl: float
    tp: float
    features: dict[str, float]


def features(s, strategy, regime, direction, entry, sl, tp):
    values = ((s.close-s.ema)/s.atr, (s.ema-s.ema_previous)/s.atr, s.adx,
              s.plus_di-s.minus_di, s.rsi, abs(s.close-s.open)/max(s.high-s.low, 1e-12),
              s.close/s.previous_close-1, s.close/s.close_3-1, s.atr_percentile,
              (s.close-s.support)/s.atr15, (s.resistance-s.close)/s.atr15,
              (s.resistance-s.support)/s.atr15, s.atr15/s.atr15_mean,
              max(s.close-s.resistance, s.support-s.close, 0)/s.atr, s.spread/s.atr,
              abs(tp-entry)/abs(entry-sl), (s.time//3600)%24, STRATEGIES[strategy],
              REGIMES[regime], (s.close-s.h1_ema)/s.h1_atr)
    return dict(zip(FEATURES, map(float, values), strict=True))


def candidates(s, regime, symbol="XAUUSD"):
    if not s.valid() or regime == "WAIT":
        return []
    result = []
    for d in (1, -1):
        strategy = None
        entry = s.close+(s.spread if d == 1 else 0)
        sl, tp = entry-d*1.5*s.atr, entry+d*3*s.atr
        if regime == ("TREND_UP" if d == 1 else "TREND_DOWN"):
            if (s.low <= s.ema if d == 1 else s.high >= s.ema) and d*(s.close-s.ema)>0 and d*(s.close-s.open)>0 and d*(s.close-s.previous_close)>0:
                strategy = "trend"
        if regime == "RANGE":
            boundary = s.support if d == 1 else s.resistance
            if abs(s.close-boundary) <= .25*s.atr15 and (s.rsi < 35 if d == 1 else s.rsi > 65) and d*(s.close-s.open)>0:
                strategy = "range"
                sl, tp = boundary-d*.5*s.atr, (s.support+s.resistance)/2
        if regime == "BREAKOUT":
            boundary = s.resistance if d == 1 else s.support
            distance = d*(s.close-boundary)
            if distance >= .1*s.atr and d*(entry-boundary) <= .5*s.atr and d*(s.close-s.open)>0 and abs(s.close-s.open)>=.6*(s.high-s.low):
                strategy = "breakout"
                tp = entry+d*3.75*s.atr
        if strategy and d*(entry-sl)>0 and d*(tp-entry)>0 and abs(tp-entry)/abs(entry-sl)>=1.5:
            sid = f"{symbol}-{s.time}-{STRATEGIES[strategy]}-{d}"
            result.append(Candidate(sid, s.time, strategy, d, entry, sl, tp,
                                    features(s, strategy, regime, d, entry, sl, tp)))
    return result


def arbitrate(items):
    if not items or len({c.direction for c in items}) != 1:
        return None
    return sorted(items, key=lambda c: (-int(c.strategy == "breakout"), c.signal_id))[0]

@dataclass
class Position:
    signal_id: str
    strategy: str
    direction: int
    entry: float
    initial_r: float
    sl: float
    tp: float
    opened: int

    def manage(self, bid, ask, atr, now, tick_size, cost_price=0, mode="hybrid"):
        d = self.direction
        price = bid if d == 1 else ask
        profit = d*(price-self.entry)
        timeout = 90 if self.strategy == "breakout" else 60
        if mode == "hybrid" and now-self.opened >= timeout*60:
            return "CLOSE", self.sl
        proposed = self.sl
        if mode != "fixed" and profit >= (.8 if self.strategy == "range" else 1)*self.initial_r:
            proposed = self.entry+d*max(cost_price, 0)
        if mode in ("hybrid", "trailing") and self.strategy != "range" and profit >= 1.5*self.initial_r:
            trail = price-d*atr*(1.2 if self.strategy == "breakout" else 1)
            proposed = max(proposed, trail) if d == 1 else min(proposed, trail)
        proposed = (math.floor(proposed/tick_size) if d == 1 else math.ceil(proposed/tick_size))*tick_size
        if d*(proposed-self.sl) >= max(.2*atr, tick_size) and d*(price-proposed)>0:
            self.sl = proposed
            return "MODIFY", proposed
        return "HOLD", self.sl

    def save(self, path):
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self)))
        tmp.replace(path)

    @classmethod
    def load(cls, path):
        p = cls(**json.loads(path.read_text()))
        if p.initial_r <= 0 or p.direction not in (-1, 1) or p.strategy not in STRATEGIES:
            raise ValueError("invalid position state")
        return p


def risk_volume(equity, entry, sl, tick_size, tick_value_loss, minimum, maximum, step):
    if min(equity, tick_size, tick_value_loss, minimum, maximum, step) <= 0 or entry == sl:
        return 0.0
    raw = equity*.005/(abs(entry-sl)/tick_size*tick_value_loss)
    volume = math.floor(min(raw, maximum)/step+1e-9)*step
    return volume if volume >= minimum else 0.0
