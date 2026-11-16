from dataclasses import replace
import pytest
from scalping_gold.core import (Snapshot, RegimeDetector, raw_regime, candidates,
                                arbitrate, Position, risk_volume, FEATURES)

@pytest.fixture
def snap():
    return Snapshot(3600, 2700, 99, 102, 98, 101, 100, 99, 100, 99.5, 2, 50,
                    30, 25, 10, 101, 99, 3, 3, 90, 110, .5, 98, 5, .1)

@pytest.mark.parametrize('direction', [1, -1])
def test_trend_both(snap, direction):
    if direction == -1:
        snap = replace(snap, open=102, close=99, previous_close=100, ema20=98,
                       ema50=102, plus_di=10, minus_di=25)
    found = candidates(snap, raw_regime(snap))
    assert len(found) == 1 and found[0].direction == direction
    assert tuple(found[0].features) == FEATURES
    assert candidates(snap, 'WAIT') == []

@pytest.mark.parametrize('direction', [1, -1])
def test_range(snap, direction):
    s = replace(snap, adx=15, open=90, low=89, high=92, close=90.5, rsi=30)
    if direction == -1:
        s = replace(s, open=110, high=111, low=108, close=109.5, rsi=70)
    c = candidates(s, raw_regime(s))[0]
    assert c.strategy == 'range' and c.direction == direction and c.tp == 100
    assert c.features['planned_rr'] >= 1.5

@pytest.mark.parametrize('direction', [1, -1])
def test_breakout(snap, direction):
    s = replace(snap, adx=15, atr15_mean=5, open=109, low=109, high=111,
                close=110.5, spread=0)
    if direction == -1:
        s = replace(s, open=91, high=91, low=89, close=89.5)
    c = candidates(s, raw_regime(s))[0]
    assert c.strategy == 'breakout' and c.direction == direction
    assert not candidates(replace(s, close=112, high=113), 'BREAKOUT')


def test_regime_hysteresis(snap):
    detector = RegimeDetector()
    assert detector.update(snap) == 'WAIT'
    assert detector.update(snap) == 'WAIT'
    assert detector.update(replace(snap, m15_time=3600)) == 'TREND_UP'
    assert detector.update(replace(snap, adx=22)) == 'WAIT'
    assert detector.update(replace(snap, atr=0)) == 'WAIT'


def test_conflict_and_priority(snap):
    a = candidates(snap, 'TREND_UP')[0]
    b = replace(a, strategy='breakout', signal_id='b')
    assert arbitrate([a, b]) == b
    assert arbitrate([a, replace(b, direction=-1)]) is None

@pytest.mark.parametrize('d', [1, -1])
def test_hybrid_recovery(tmp_path, d):
    p = Position('id', 'trend', d, 100, 2, 100-d*2, 100+d*4, 0)
    action, sl = p.manage(100+d*3.5, 100+d*3.5, 1, 100, .01, .1)
    assert action == 'MODIFY' and d*(sl-100)>0
    old = p.sl
    p.manage(100+d*.5, 100+d*.5, 1, 110, .01)
    assert p.sl == old and p.initial_r == 2
    path = tmp_path/'state.json'
    p.save(path)
    assert Position.load(path) == p
    assert p.manage(100, 100, 1, 3600, .01)[0] == 'CLOSE'


def test_sell_uses_ask_and_range_no_trail():
    p = Position('id', 'range', -1, 100, 2, 102, 95, 0)
    assert p.manage(97, 99, 1, 10, .01)[0] == 'HOLD'
    p.manage(96, 96.1, 1, 10, .01)
    assert p.sl == 100

@pytest.mark.parametrize('tick', [.001, .01, .1, .25])
def test_risk(tick):
    v = risk_volume(10000, 2000, 1995, tick, tick*100, .01, 100, .01)
    assert v == .1
    assert risk_volume(1, 2000, 1995, tick, tick*100, .01, 100, .01) == 0
