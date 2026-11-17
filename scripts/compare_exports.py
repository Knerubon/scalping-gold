"""Compare EA candidate requests against historical Python candidate feature rows."""

import argparse
import json
import math

from scalping_gold.core import FEATURE_HASH, FEATURES


def compare(ea_path, python_path, tolerance=1e-7):
    def load(path):
        with open(path) as f:
            return {row["signal_id"]: row for line in f if (row := json.loads(line))}

    ea, reference = load(ea_path), load(python_path)
    if set(ea) != set(reference):
        raise ValueError(
            f"signal differences: EA only {len(set(ea) - set(reference))}, Python only {len(set(reference) - set(ea))}; use identical periods and warmup"
        )
    if not ea:
        raise ValueError("no candidate observations; parity not established")
    for sid, row in ea.items():
        assert row["feature_hash"] == FEATURE_HASH
        for name in FEATURES:
            assert math.isclose(
                row["features"][name],
                reference[sid]["features"][name],
                rel_tol=tolerance,
                abs_tol=tolerance,
            ), (sid, name)
    print(f"PASS: {len(ea)} candidate IDs and feature snapshots match")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("ea_export")
    p.add_argument("python_export")
    a = p.parse_args()
    compare(a.ea_export, a.python_export)
