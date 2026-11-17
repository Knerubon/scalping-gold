"""Compare identical OOS candidate IDs/costs across both gates and four exits."""

import argparse
import json
from pathlib import Path

import pandas as pd

from scalping_gold.replay import metrics, portfolio


def evaluate(data, artifacts):
    root, models = Path(data), Path(artifacts)
    scores = {
        kind: pd.read_csv(models / kind / "test-scores.csv").set_index("signal_id")
        for kind in ("logistic", "lightgbm")
    }
    labels = {
        mode: pd.read_csv(root / f"labels-{mode}.csv").set_index("signal_id")
        for mode in ("fixed", "be", "trailing", "hybrid")
    }
    common = set.intersection(*[set(df.index) for df in [*scores.values(), *labels.values()]])
    if not common:
        raise ValueError("no common out-of-sample candidates")
    results = {"candidate_count": len(common), "matrix": {}}
    for mode, rows in labels.items():
        rows = rows.loc[rows.index.isin(common)].sort_values("time")
        results["matrix"][mode] = {"ea_only": metrics(portfolio(rows).net_r)}
        for kind, frame in scores.items():
            manifest = json.loads((models / kind / "manifest.json").read_text())
            keep = (frame.p_win >= manifest["threshold"]) & (frame.expected_r > 0)
            keep = keep.reindex(rows.index, fill_value=False)
            results["matrix"][mode][kind] = {
                **metrics(portfolio(rows, keep).net_r),
                "rejection_rate": float(1 - keep.mean()),
            }
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data")
    p.add_argument("artifacts")
    p.add_argument("--output", default="artifacts/comparison.json")
    a = p.parse_args()
    Path(a.output).write_text(json.dumps(evaluate(a.data, a.artifacts), indent=2, allow_nan=False))
