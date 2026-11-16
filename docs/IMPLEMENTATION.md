# Implementation record
Source: Issue #1, read in full 2026-11-16. Initial repo empty, no local instructions.
Root empty main commit establishes PR base; all implementation on feature/scalping-gold-v1.
No NEXORA accessed. MetaEditor unavailable.
Assumptions: range uses preceding 20 closed M15 bars; only fully closed M5/M15/H1 data.
H1 context is a feature; no unspecified directional veto. Unsafe regimes immediately WAIT.
Conflicting candidates abstain. OHLC replay uses stop-first ambiguity and adverse gaps;
SL modifications apply next bar. Timeout is a separate outcome class.
Spread limit 50 broker points requires calibration. Broker UTC offset is explicit.
No approved model or market dataset bundled. Synthetic tests are mechanics evidence only.
Phases: deterministic reference; EA safety/exits; ML/service/replay; validation/draft PR.

Phase 1 complete: deterministic strategy predicates, hysteresis, arbitration,
feature order/hash, risk sizing and hybrid exits with persistence reference.
Validation: pytest 15 passed. MT5 parity still pending native validation.

Phase 2: MQL5 closed-bar loader, strategy/regime modules, candidate export,
strict response matching, tester replay path, demo-only orders with SL/TP,
risk/volume/margin/spread checks, account/symbol mutex, write-ahead journal,
restart recovery, broker-aware BE/trailing/time exits, daily history locks.
Validation: Python suite 15 passed; native compiler unavailable, so source review
is not evidence of compilation. Broker fill/gap/restart behavior pending MT5.

Phase 3 complete: UTC historical data validation/aggregation and availability-time
joins, indicator/features reference, conservative OHLC labels, identical-cost exit
ablations, Logistic Regression and LightGBM, held-out sigmoid calibration,
purged/embargoed partitions and expanding walk-forward reports, immutable hashed
artifacts, default-unapproved loopback inference, strict schema and tester replay.
Validation: 46 tests passed (includes both actual model fits on synthetic labels).
No market data, OOS trading evidence, approved model or profitability result exists.
One dependency deprecation warning remains; it does not affect test results.
