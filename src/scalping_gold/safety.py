"""Testable execution-guard reference with durable, atomic submission reservation.

This module never connects to a broker. The terminal implements the equivalent
policy in MQL5; native tests are required in addition to these policy tests.
"""

import sqlite3
from pathlib import Path


class GuardLedger:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS days(day INTEGER PRIMARY KEY, equity REAL, trades INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, locked INTEGER DEFAULT 0)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS submissions(signal TEXT PRIMARY KEY, status TEXT)"
        )

    def observe(self, day, equity, baseline=None, closed_net=None):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT OR IGNORE INTO days(day,equity,locked) VALUES(?,?,?)",
                (day, baseline or equity, int((baseline or equity) <= 0)),
            )
            base, losses = self.db.execute(
                "SELECT equity,losses FROM days WHERE day=?", (day,)
            ).fetchone()
            if closed_net is not None:
                losses = losses + 1 if closed_net < 0 else 0
            self.db.execute(
                "UPDATE days SET losses=?,locked=MAX(locked,?) WHERE day=?",
                (losses, int(equity <= base * 0.98 or losses >= 3), day),
            )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def reserve(
        self,
        signal,
        day,
        *,
        account_mode,
        auto=False,
        emergency=False,
        exposure=False,
        inference="ABSTAIN",
        protective_stops=False,
    ):
        if (
            account_mode != "DEMO"
            or not auto
            or emergency
            or exposure
            or inference != "APPROVE"
            or not protective_stops
        ):
            return False
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT trades,locked FROM days WHERE day=?", (day,)).fetchone()
            unresolved = self.db.execute(
                "SELECT 1 FROM submissions WHERE status='pending' LIMIT 1"
            ).fetchone()
            if row is None or row[0] >= 5 or row[1] or unresolved:
                self.db.execute("ROLLBACK")
                return False
            try:
                self.db.execute("INSERT INTO submissions VALUES(?,'pending')", (signal,))
            except sqlite3.IntegrityError:
                self.db.execute("ROLLBACK")
                return False
            self.db.execute("UPDATE days SET trades=trades+1 WHERE day=?", (day,))
            self.db.execute("COMMIT")
            return True
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def reconcile(self, signal, status):
        if status not in ("filled", "partial", "rejected"):
            raise ValueError("ambiguous result must remain pending")
        self.db.execute("UPDATE submissions SET status=? WHERE signal=?", (status, signal))

    def close(self):
        self.db.close()
