"""Historical extraction, labeling, exit ablations and timestamp-valid replay."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .core import FEATURE_HASH, FEATURE_VERSION
from .data import extract, read_bars
from .replay import Costs, label_candidates, metrics, portfolio


def prepare(bars_path, output, costs, symbol="XAUUSD", server_offset=0):
    df = read_bars(bars_path)
    selected = list(extract(df, symbol))
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "candidates.jsonl").open("w") as f:
        for c in selected:
            f.write(json.dumps(asdict(c), allow_nan=False) + "\n")
    reports = {"costs": asdict(costs), "candidate_count": len(selected), "exit_modes": {}}
    reports.update(
        source_sha256=hashlib.sha256(Path(bars_path).read_bytes()).hexdigest(),
        symbol=symbol,
        server_utc_offset_minutes=server_offset,
    )
    for mode in ("fixed", "be", "trailing", "hybrid"):
        labels = label_candidates(selected, df, costs, mode)
        if not labels.empty:
            labels["server_day"] = (labels.time + server_offset * 60) // 86400
        labels.to_csv(root / f"labels-{mode}.csv", index=False)
        reports["exit_modes"][mode] = (
            metrics(portfolio(labels).net_r) if not labels.empty else metrics([])
        )
    (root / "exit-comparison.json").write_text(json.dumps(reports, indent=2, allow_nan=False))
    return reports


def export_decisions(scores_path, candidate_path, manifest_path, output, symbol="XAUUSD"):
    """Exports unapproved test decisions as ABSTAIN until separately reviewed.

    Research gate APPROVE decisions need explicit approval file and verified OOS
    evidence via Scorer. There is no flag that bypasses model approval.
    """
    import os

    from .service import Scorer

    manifest = json.loads(Path(manifest_path).read_text())
    scorer = Scorer(Path(manifest_path).parent, os.getenv("SG_APPROVAL"))
    eligible = pd.read_csv(scores_path)
    ids = set(eligible.signal_id)
    with open(candidate_path) as f:
        candidates = [json.loads(line) for line in f if line.strip()]
    with open(output, "w") as f:
        for c in candidates:
            if c["signal_id"] not in ids or c["time"] <= manifest["threshold_through"]:
                continue
            from .protocol import Request

            t = c["time"]
            request = Request(
                schema_version="1",
                signal_id=c["signal_id"],
                symbol=symbol,
                strategy_id=c["strategy"],
                direction=c["direction"],
                closed_bar_utc=t,
                feature_version=FEATURE_VERSION,
                feature_hash=FEATURE_HASH,
                model_version=manifest["model_version"],
                model_hash=manifest["model_hash"],
                timestamp=t,
                expires_at=t + 300,
                features=c["features"],
            )
            response = scorer.score(request, now=t)
            f.write(response.model_dump_json() + "\n")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("bars")
    prep.add_argument("--symbol", default="XAUUSD")
    prep.add_argument("--server-utc-offset-minutes", type=int, default=0)
    prep.add_argument("--output", default="artifacts/data")
    prep.add_argument("--tick-size", type=float, default=0.01)
    prep.add_argument("--slippage", type=float, default=0.05)
    prep.add_argument("--commission", type=float, default=0.10)
    prep.add_argument("--be-allowance", type=float, default=0.20)
    replay = sub.add_parser("replay")
    replay.add_argument("scores")
    replay.add_argument("candidates")
    replay.add_argument("manifest")
    replay.add_argument("output")
    replay.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(
            args.bars,
            args.output,
            Costs(args.tick_size, args.slippage, args.commission, args.be_allowance),
            args.symbol,
            args.server_utc_offset_minutes,
        )
    else:
        export_decisions(args.scores, args.candidates, args.manifest, args.output, args.symbol)


if __name__ == "__main__":
    main()
