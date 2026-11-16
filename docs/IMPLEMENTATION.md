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
