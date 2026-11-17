import pytest

from scalping_gold.safety import GuardLedger


def reserve(ledger, signal="id", **changes):
    kwargs = dict(account_mode="DEMO", auto=True, protective_stops=True, inference="APPROVE")
    kwargs.update(changes)
    return ledger.reserve(signal, 1, **kwargs)


@pytest.mark.parametrize(
    "changes",
    [
        dict(account_mode="REAL"),
        dict(account_mode="CONTEST"),
        dict(auto=False),
        dict(emergency=True),
        dict(exposure=True),
        dict(inference="ABSTAIN"),
        dict(inference="REJECT"),
        dict(protective_stops=False),
    ],
)
def test_entry_guards(tmp_path, changes):
    ledger = GuardLedger(tmp_path / "state.db")
    ledger.observe(1, 10000)
    assert not reserve(ledger, **changes)
    ledger.close()


def test_duplicate_partial_restart_and_unknown(tmp_path):
    path = tmp_path / "state.db"
    ledger = GuardLedger(path)
    ledger.observe(1, 10000)
    assert reserve(ledger)
    ledger.close()
    ledger = GuardLedger(path)
    assert not reserve(ledger, "another")
    with pytest.raises(ValueError):
        ledger.reconcile("id", "timeout")
    ledger.reconcile("id", "partial")
    assert not reserve(ledger)
    assert not reserve(ledger, "another", exposure=True)
    assert reserve(ledger, "another")
    ledger.close()


def test_daily_loss_and_streak_lock_persist(tmp_path):
    ledger = GuardLedger(tmp_path / "state.db")
    ledger.observe(1, 10000)
    ledger.observe(1, 9799)  # realized + floating equity
    ledger.observe(1, 10100)
    assert not reserve(ledger)
    ledger.observe(2, 10000)
    for _ in range(3):
        ledger.observe(2, 9990, closed_net=-1)
    ledger.observe(2, 10010, closed_net=100)
    assert not ledger.reserve(
        "x", 2, account_mode="DEMO", auto=True, inference="APPROVE", protective_stops=True
    )
    ledger.close()


def test_five_trade_cap(tmp_path):
    ledger = GuardLedger(tmp_path / "state.db")
    ledger.observe(1, 10000)
    for i in range(5):
        assert reserve(ledger, str(i))
        ledger.reconcile(str(i), "filled")
    assert not reserve(ledger, "six")
    ledger.close()


def test_two_connections_cannot_reserve_two_orders(tmp_path):
    path = tmp_path / "state.db"
    first, second = GuardLedger(path), GuardLedger(path)
    first.observe(1, 10000)
    assert reserve(first, "a")
    assert not reserve(second, "b")
    first.close()
    second.close()


def test_auto_defaults_disabled(tmp_path):
    ledger = GuardLedger(tmp_path / "state.db")
    ledger.observe(1, 10000)
    assert not ledger.reserve(
        "id", 1, account_mode="DEMO", protective_stops=True, inference="APPROVE"
    )
    ledger.close()
