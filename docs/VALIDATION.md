# Validation report and outstanding native acceptance

## Evidence actually obtained

Environment: Linux x86_64, Python 3.12.14. Exact installed package versions are
in `python-tested.txt`. MetaEditor, MT5 terminal and Wine were not found on PATH.
No EX5 compilation, MT5 Strategy Tester run, broker connection, account deployment
or automatic trading enablement was performed. No real historical market dataset
or approved model was supplied. Synthetic training results are not trading evidence.

Phase checks: phase 1: 15 Python tests passed; phase 2: 15 passed; phase 3:
46 passed. Final verification: **59 tests passed**, one dependency deprecation warning.
Ruff: all checks passed. `pip check`: no broken requirements. `git diff --check`
passed. Captured output is in [test-results.txt](test-results.txt).

Automated coverage includes BUY/SELL trend, range and breakout predicates;
compression versus range-width rules; repeated/changed M15 regime closes; conflict
arbitration; versioned feature order/hash; tick-size risk sizing; immutable R and
position persistence; bid/ask exit sides; monotonic stops, BE/trailing/time exit;
OHLC stop-first ambiguity, adverse gaps and missing horizons; incomplete higher
bars; future-data mutation at all three M5 offsets within M15; explicit range
availability at signal open; purged/embargoed validation; actual calibrated fits
of both models on synthetic labels; walk-forward reporting; artifact corruption;
missing/unapproved/future model refusal; malformed/stale/wrong-direction responses;
latency abstention; persistent policy locks; duplicate, partial and uncertain
submissions across reference-ledger restart; two-ledger atomic reservation;
and real loopback Uvicorn startup/health/schema handling.

`test_source_contract.py` checks MQL5 feature/API field wiring and nearby demo
checks. These are **source assertions**, not execution or compilation tests.
The Python safety ledger tests a policy reference, not MT5 order behavior.
Native `GoldCoreTests.mq5` and export comparison utilities are supplied but have
not been run. Final acceptance of native parity remains pending.

## Review findings resolved

- Daily equity guard now runs while positions are open, retaining a floating-loss
  lock even if equity subsequently recovers. History reconstructs whether three
  consecutive losses occurred earlier in the day, even after subsequent wins.
- Ambiguous requests burn the signal and retain a persistent uncertainty lock;
  a confirmed position or explicit operator reconciliation is required.
- Initial R uses actual position entry and journaled initial SL, after entry order
  finalization; it is never reconstructed from a trailed stop. An unexpected
  entry-price change invalidates recovery. Trend/breakout TP is reconciled to
  actual R; the originally submitted broker protection remains during adjustment.
- JSON duplicate keys, noncanonical numbers, incompatible fields, probability
  normalization errors and stale responses abstain. Boolean/float directions are
  rejected by the Python schema.
- Higher-timeframe range Series are converted to arrays before changing their
  availability index, preventing pandas alignment from exposing the current M15
  bar. Prefix/future-mutation tests cover all M5 positions within M15.
- Breakout anti-chase distance is rechecked on the post-inference execution quote.
- State keys include hashed account login/server/symbol. A second chart cannot
  overwrite an existing submission mutex during initialization.

## Native acceptance matrix — all pending

Perform only in a dedicated DEMO installation or local Strategy Tester after
compilation. See README for exact file paths and commands.

| Check | Required evidence |
|---|---|
| Compile EA, GoldCoreTests, ExportBars | Terminal/MetaEditor builds, complete log, EX5 hash, errors resolved |
| Native strategy fixture parity | GoldCoreTests failures=0; Python CSV comparison passes |
| Historical indicator/feature parity | Same input history, seed/warmup, UTC offset and period; no missing IDs, feature differences within justified tolerance |
| REAL and CONTEST lock | Initialization fails; no order requests; account enum recorded |
| Default/shadow/emergency modes | No new entry; broker protection remains; management active with trading permission |
| Inference failures | Timeout, HTTP offline, malformed/stale/mismatched/unapproved response never opens a position |
| BUY and SELL executions | One correct direction, volume step/min/max, explicit SL/TP, correct request/fill retcodes |
| Broker property variations | Gold 2/3 digits, nondecimal tick step, stop/freeze thresholds, spread spikes, insufficient margin |
| Duplicate/multiple charts | Same signal and conflicting charts cannot open duplicate positions |
| Partial/PLACED/timeout | Finalized actual entry/R, remaining volume not resubmitted, uncertain status blocks new entries |
| Hybrid exits | Actual-fill R constant; correct side; targets 2/2.5R or range midpoint; BE costs; no backward SL; step >=0.2 ATR and tick |
| Restart | Restart before submission, after send/before state save, after BE/trail, missing journal, broker history unavailable |
| Missing protection | Emergency close attempt; no further entry while unprotected exposure exists |
| Daily risk locks | 5 trades, 2% realized+floating equity loss, 3 consecutive complete-position losses, commissions/partials included, server-day rollover |
| Gaps and trade errors | Reject/freeze/off-quotes/disconnection handled; broker stops remain; no optimistic fills assumed |
| Tester replay | Correct UTC-only OOS decisions; future/stale/mismatched IDs refused; real-tick reports saved |
| Model/exit comparison | Same OOS IDs/data/costs for baseline, LR, LGBM and all four exit modes; full matrix with counts and rejections |
| Shadow latency | Local HTTP p50/p95/p99, decision counts/reasons, <=2 second response handling |

## Known technical limitations and risks

1. **Native implementation unverified:** MQL5 compiler correctness, indicator seeds
   (especially Wilder ADX), terminal event ordering, broker fill modes, actual
   recovery and retcodes require the matrix above. Python and MQL5 implementations
   can diverge; schema hashes alone do not establish numerical parity.
2. **OHLC research approximation:** no ticks or broker execution feed was provided.
   Stop-first is conservative for ambiguous touches, but cannot reproduce tick
   paths, variable within-bar spreads, queue latency, swaps, stop slippage, broker
   commissions or all terminal freeze rules. Full-hybrid labels share the exit
   policy, not an assertion of identical fills. Calibrate all costs per broker.
3. **Risk estimates:** 0.5% uses calculated SL loss before unknown commission and
   adverse market slippage; gaps can exceed planned loss. BE is a cost allowance,
   not a guarantee. Offline portfolio drawdown is in R and daily locking is based
   on completed trades; intratrade floating losses require the native tick test.
4. **UTC/session and seed assumptions:** broker offsets including DST are manual;
   input bars are UTC M5 bid bars with point spread converted to price. Historical
   MqlRates spread need not equal live executable spread. Higher bars are derived
   from M5; compare them with actual broker M15/H1 history before model approval.
5. **Persistence scope:** terminal Global Variables and the journal are local to
   one terminal data folder. Different machines/terminals are not coordinated.
   Manual/third-party orders can bypass controls. A stale mutex or uncertain
   request intentionally needs operator reconciliation; locks are never silently
   cleared. History scans are intentionally simple and can become slow on a very
   large account history; profile native latency before a demo trial.
6. **Day baseline:** first attach while flat reconstructs midnight cash balance;
   a missing baseline with any account exposure locks the day. Continuous rollover
   uses equity at the first observed quote, not an unavailable midnight tick.
   Cash flows and unrelated account exposure can conservatively trigger locks.
7. **Availability:** without terminal connectivity/trading permission, BE/trailing,
   emergency closes and time exits cannot execute. Existing broker SL/TP are the
   only protection while the terminal is stopped. ML HTTP is synchronous and can
   delay management up to the bounded two-second request; broker stops stay active.
8. **Approval is human governance:** the service verifies hashes and chronology;
   it cannot prove a reviewer inspected real data. Joblib artifacts and local
   approval files must be trusted and protected. No service authentication exists;
   bind only to 127.0.0.1. No model is approved or enabled by this implementation.
9. **Evaluation scope:** no genuine OOS evidence, profitability result, model
   improvement, broker-calibrated spread threshold or live latency distribution
   exists. Walk-forward fold test windows can overlap; don't aggregate them as
   independent observations. Fixed/BE/trailing label horizons are dataset-censored
   at the strategy horizon for comparison, which is explicitly distinguished from
   a native time-exit order.
10. One harmless Starlette/AnyIO deprecation warning is present in test dependencies.
    It is retained in the test evidence instead of being suppressed.
