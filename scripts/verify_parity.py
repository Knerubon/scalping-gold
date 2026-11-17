"""Compare terminal GoldCoreTests.csv with Python's six deterministic candidates.

Run the native script first; do not use this utility as a substitute for MT5.
"""

import argparse
import csv
import math
from dataclasses import replace

from scalping_gold.core import FEATURES, Snapshot, candidates, raw_regime


def fixtures():
    s = Snapshot(
        3600,
        2700,
        99,
        102,
        98,
        101,
        100,
        99,
        100,
        99.5,
        2,
        50,
        30,
        25,
        10,
        101,
        99,
        3,
        3,
        90,
        110,
        0.5,
        98,
        5,
        0.1,
    )
    return [
        s,
        replace(s, open=102, close=99, ema20=98, ema50=102, plus_di=10, minus_di=25),
        replace(s, adx=15, open=90, low=89, high=92, close=90.5, rsi=30),
        replace(s, adx=15, open=110, high=111, low=108, close=109.5, rsi=70),
        replace(s, adx=15, atr15_mean=5, open=109, low=109, high=111, close=110.5, spread=0),
        replace(s, adx=15, atr15_mean=5, open=91, high=91, low=89, close=89.5, spread=0),
    ]


def compare(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6, "six native scenarios required"
    for row, s in zip(rows, fixtures(), strict=True):
        c = candidates(s, raw_regime(s))[0]
        expected = [c.entry, c.sl, c.tp, *[c.features[f] for f in FEATURES]]
        names = ["entry", "sl", "tp", *FEATURES]
        assert row["signal_id"] == c.signal_id
        for name, value in zip(names, expected, strict=True):
            assert math.isclose(float(row[name]), value, rel_tol=1e-9, abs_tol=1e-9), name
    print("PASS: six native candidate and feature snapshots match Python")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("native_csv")
    compare(parser.parse_args().native_csv)
