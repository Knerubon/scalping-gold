# Scalping Gold V1

Research MT5 Expert Advisor for **XAUUSD DEMO accounts only**, with an offline
Python ML filter. Implementation of [Issue #1](https://github.com/Knerubon/scalping-gold/issues/1).
Automatic trading defaults to **false**. Nothing in this repository deploys to a
terminal, enables Algo Trading, approves a model or supports real/contest accounts.
This project is independent of NEXORA.

**Status:** Python mechanics tested on synthetic fixtures. MQL5 source has not
been compiled here; MT5/MetaEditor is unavailable. No historical market evaluation,
profitability, live execution or feature/indicator parity is claimed. Read
[validation and limitations](docs/VALIDATION.md) before running the EA.

## Architecture

- `mql5/GoldCore.mqh`: deterministic M5 strategy predicates, M15 regime/hysteresis,
  H1 feature context, arbitration and a versioned 20-feature snapshot.
- `mql5/ScalpingGold.mq5`: closed-bar loader, state machine, export, local inference
  or timestamp-valid Tester replay, broker checks, persistent journal and exits.
- `src/scalping_gold/core.py`: independently testable strategy/exit reference.
- `data.py`, `replay.py`: UTC preparation, candidate extraction, conservative
  outcome simulation, costs, one-position evaluation and exit ablations.
- `train.py`: Logistic Regression baseline and LightGBM challenger, held-out
  calibration, purged splits, embargo, threshold validation and walk-forward.
- `protocol.py`, `service.py`: strict versioned API and frozen artifact loading.
- `safety.py`: durable execution-policy test harness; it never sends broker orders.
- `mql5/GoldCoreTests.mq5`, `scripts/verify_parity.py`: native fixture parity tests.

M5 closed signals feed M15 ADX/DI/EMA regime detection, with H1 context as a feature.
ADX 20–25/conflicts abstain. Safe regimes require two distinct closed M15 bars;
unsafe conditions immediately reset to WAIT. Range bounds use the preceding 20
M15 bars available at the M5 signal's **open**. Compressed ranging markets permit
breakout setups. One candidate is selected; conflicts abstain. ML can approve or
reject that candidate and cannot originate or reverse a trade.

Strategies implement Trend Pullback (1.5 ATR SL, 2R target), Range Reversal
(structural SL, midpoint target only at RR >=1.5), and Breakout (compression,
body/close confirmation and anti-chase, 1.5 ATR SL, 2.5R target).

## Python installation and tests

Python 3.11 or 3.12, a C++ runtime supported by LightGBM, and local writable storage
are required. From this repository:

```sh
python -m venv .venv
# Linux/macOS; Windows PowerShell: .venv\Scripts\Activate.ps1
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pip check
python -m pytest -q
python -m ruff check src tests scripts
```

The CI workflow runs Python/contract checks. It does **not** compile MQL5.
Tested dependency versions are recorded in `docs/python-tested.txt`.

## Compile in MT5 — exact manual steps

1. Install the Windows MetaTrader 5 terminal and MetaEditor. Use a dedicated
   **demo** login; confirm its `ACCOUNT_TRADE_MODE` is DEMO. Leave the terminal's
   Algo Trading button OFF. REAL and CONTEST fail initialization.
2. In MT5 choose **File → Open Data Folder**. Create
   `MQL5/Experts/ScalpingGold/`. Copy `ScalpingGold.mq5`, `GoldCore.mqh` and
   `GoldJson.mqh` from `mql5/` into that folder.
3. Press **F4**, open that `ScalpingGold.mq5` in MetaEditor, and press **F7**.
   Record the complete compiler output, terminal build and generated EX5 hash.
   Resolve every error and review warnings before proceeding. No EX5 is supplied.
4. Create `MQL5/Scripts/ScalpingGoldTests/`. Copy `GoldCoreTests.mq5`,
   `GoldCore.mqh`, `GoldJson.mqh`, and `ExportBars.mq5` there. Open and compile
   each `.mq5` with F7. Run `GoldCoreTests` on a demo chart. It sends no orders.
   Require `GoldCoreTests failures=0` in Experts. Copy the resulting
   `MQL5/Files/GoldCoreTests.csv` to the repository and run:

   ```sh
   python scripts/verify_parity.py GoldCoreTests.csv
   ```

5. Verify the broker's XAUUSD symbol suffix, digits, tick size, tick value, stops,
   freeze levels, volume steps, commission, swap and spread. Configure inputs for
   those properties. Attach the EA to **that symbol's M5 chart** only. Load
   `config/demo-shadow.set`, keeping `AUTO_TRADING=false`.
6. Verify the broker UTC offset, including DST. `BrokerUtcOffsetMinutes=0` is an
   example, not an autodetected timezone. Incorrect offset invalidates feature
   parity, session features and replay matching.

An optional command-line compile on Windows is
`metaeditor64.exe /compile:"C:\...\MQL5\Experts\ScalpingGold\ScalpingGold.mq5" /log`.
The exact executable and data-folder paths depend on the installation.

## Historical preparation and evaluation

Run the read-only `ExportBars` script on a terminal with downloaded M5 history.
Configure `FromServer`, `ToServer`, symbol and UTC offset. Split exports at offset
changes, join without duplicate timestamps, and verify continuity. Copy
`MQL5/Files/gold-m5.csv` to a local `data/` directory. CSV columns are
`time,open,high,low,close,spread`: UTC ISO timestamps of **bar opens**, bid OHLC,
and spread in **price units**, not broker points. Only complete higher-timeframe
buckets are used. Supply at least 250 closed H1 bars of warmup before evaluation.

```sh
python -m scalping_gold.cli prepare data/gold-m5.csv --output artifacts/data \
  --symbol XAUUSD --server-utc-offset-minutes 0 \
  --tick-size 0.01 --slippage 0.05 --commission 0.10 --be-allowance 0.20
python -m scalping_gold.train artifacts/data/labels-hybrid.csv \
  --output artifacts/models --version gold-v1-research
python scripts/evaluate_matrix.py artifacts/data artifacts/models \
  --output artifacts/comparison.json
```

All cost values above are **examples requiring broker calibration**. Set the symbol suffix and server offset to the same values as the EA. Commission
is round-trip account currency converted into price distance per unit position.
Spread is already included using the quote side. The label simulation uses actual
modeled entry versus initial SL for immutable R; BE/trailing use Bid for long exits
and Ask for short exits. Targets for trend/breakout use actual R. Stop-first
intrabar ambiguity, adverse stop gaps and adverse slippage avoid optimistic fills.
New stops apply on the following bar. Timeout remains a distinct class even if
net R is positive. Missing end-of-horizon data is not labeled.

Output includes candidates, labeled net R/outcomes, fixed/BE/trailing/hybrid
ablations, OOS probability scores, calibrated log loss/Brier/ECE, trade counts,
rejections, profit factor, expectancy and drawdown. The matrix utility restricts
comparisons to common OOS IDs with identical costs. The portfolio is a research
approximation; intratrade floating-risk lock and broker execution need MT5 ticks.

Fit, calibration, threshold validation and test are chronologically separate.
Earlier labels crossing the next partition boundary are removed, followed by a
five-minute embargo. Walk-forward uses expanding prefixes and reports each fold
separately; overlapping fold reports must not be summed as independent trades.
Thresholds use validation only; final test results never tune them. Training
refuses missing outcome classes or insufficient purged data. Both models are
saved **unapproved** with SHA256 and feature metadata. Do not load untrusted
joblib files: Python deserialization can execute code even when a hash matches.

## Inference, shadow mode and model approval

Run on the **same Windows machine as MT5** (127.0.0.1 inside a different machine
is a different service). In an activated Python environment:

```sh
# PowerShell equivalent: $env:SG_ARTIFACT="artifacts/models/logistic"
export SG_ARTIFACT=artifacts/models/logistic
python -m uvicorn scalping_gold.service:app --host 127.0.0.1 --port 8000 --log-level info
```

`GET /health` reports whether a model is loaded and approved. `POST /score` accepts
only the strict request schema in `protocol.py`; `/docs` describes it. The EA pins
feature and model versions/hashes and enforces a maximum two-second timeout.
Unavailable, invalid, stale, incompatible or unapproved predictions abstain.
Responses carry three calibrated probabilities, estimated net R and a reason.
All response fields are scalars for the EA's strict flat JSON parser. Scoring
logs contain structured decisions and latency; enable Python INFO logging when
collecting latency evidence (see `scripts/serve.py`).

For HTTP shadow evaluation, set `ApprovedModelVersion/Hash` to the loaded
manifest's values but leave `AUTO_TRADING=false`. The service still ABSTAINS until
human approval. EA exports candidates to `MQL5/Files/scalping-gold-candidates.jsonl`;
service logs show shadow scores. `scalping-gold-plans.jsonl` also records planned entry/SL/TP with the full candidate request. Check exported feature parity against identical
Python periods using `scripts/compare_exports.py` **before any model approval**.
There are no bundled approved artifacts or fabricated evaluation results.

After genuine OOS evidence, native parity and the demo validation checklist have
been reviewed, copy `config/approval.example.json` to a local, ignored approval
file. A human reviewer supplies the exact model SHA256, the SHA256 of
`artifacts/models/evaluation.json`, their name and `approved=true`. Set
`SG_APPROVAL` to that local file and restart the service. Approval is an explicit
human research decision, not a profitability guarantee. The service checks the
hashes, non-synthetic report flag and chronological evaluation separation.
The deployment model is frozen; there is no online self-training.

## Strategy Tester and replay

HTTP is not assumed to work inside MT5 Strategy Tester. First generate replay
from **untouched OOS** candidates and a reviewed frozen artifact:

```sh
# SG_APPROVAL must reference the reviewed evidence, otherwise decisions ABSTAIN.
python -m scalping_gold.cli replay \
  artifacts/models/logistic/test-scores.csv artifacts/data/candidates.jsonl \
  artifacts/models/logistic/manifest.json artifacts/logistic-replay.jsonl
```

Copy this file into the Tester's agent-accessible `MQL5/Files/` directory, set
`ReplayFile=logistic-replay.jsonl`, and pin the exact manifest model version/hash.
For portable local-agent file copying, add `#property tester_file "logistic-replay.jsonl"`
to a **local copy** of the EA before compiling; MetaTrader requires this directive
for an input-defined file. Do not use remote/cloud agents with unreviewed data.
The EA matches candidate ID, direction, strategy, symbol, feature/model versions,
closed UTC time and expiry; pre-training and stale decisions cannot execute.

Press **Ctrl+R** in MT5, select ScalpingGold, the exact broker symbol, M5,
**Every tick based on real ticks**, demo deposit/currency/leverage and a date range
strictly after the artifact's threshold-validation horizon. Include warmup before
counting results. Start with `AUTO_TRADING=false` and require candidate/export
parity. For simulated Tester orders only, explicitly select `AUTO_TRADING=true`
in Tester inputs after the prior checks; this does not authorize connecting to
an account. No real account mode is permitted even in Tester. The template
`config/tester.example.ini` supplies conservative examples, not validated settings.

Run the manual acceptance matrix in `docs/VALIDATION.md`: BUY/SELL, broker digit
variations, stop/freeze rejections, slippage/gaps, partial fills, restart and offline
ML. Save the Tester report, inputs, journal, compiler log and data/model hashes.

## Demo execution controls and recovery

No account deployment or Algo Trading enablement has been performed. If a human
later chooses a demo trial, they must separately enable the terminal's Algo
Trading permission, the EA's trading permission, and `AUTO_TRADING=true`, with a
reviewed matching model and local HTTP allowlist entry
**Tools → Options → Expert Advisors → Allow WebRequest for listed URL**:
`http://127.0.0.1:8000`. Default sample settings leave execution disabled.

Every trade request rechecks the account's DEMO enum. New entries require 0.5%
equity risk sizing, at most one symbol exposure, at most five trades per server
day, a persistent 2% equity drawdown lock, and a lock after three consecutive
closed losses. The limits include manual trades on the configured symbol. Stops,
volume, margin, spread, tradability, quote age, response identity and retcodes are
checked. No martingale, grid or averaging down exists. These controls cannot
prevent trades placed by other programs or other terminals.

Trend/breakout BE triggers at 1R, trailing at 1.5R, distances 1/1.2 closed M5 ATR;
range BE triggers at 0.8R with no trail. SL updates improve by at least 0.2 ATR and
one tick. Broker stop/freeze levels are enforced. Time exits are 60/60/90 minutes.
BE cost allowance is configurable; it never guarantees zero loss. Broker SL/TP
remain active while HTTP is offline. `EmergencyStop=true` or `AUTO_TRADING=false`
halts new entries and preserves exit management and protective stops.

Terminal Global Variables persist initial R/strategy, daily equity locks, last
submitted bar, pending journal and uncertainty flag. Keys hash login, server and
symbol. Keep the terminal data folder intact. An uncertain submission or stale
mutex blocks entries until an operator reconciles broker history, positions,
orders and logs. **Never clear locks merely to resume trading.** If state is
missing, retain broker protection and use a conservative 60-minute exit; new
entries remain blocked while the unknown position exists. A first mid-day start
with open account exposure and no daily equity baseline locks the day. The
terminal must stay running/connected for BE, trailing and time exits; broker
SL/TP are the only server-side exits.

Troubleshooting: `shadow_or_unavailable` health means inspect artifact hashes and
approval; HTTP errors mean verify same-machine loopback/allowlist; missing signals
mean inspect history warmup, regime confirmation, spread and chart symbol/period;
missing replay approvals mean check UTC offsets, OOS dates, signal IDs and expiry.
See the validation report for unresolved native-execution limitations.
