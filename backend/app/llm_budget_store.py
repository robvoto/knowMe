"""Transactional daily AI token reservations shared by local server processes.

This is a building block for migration from the legacy JSON usage ledger. It is
not yet wired into live requests: doing that requires migration and reconciliation.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
import time
import uuid
from pathlib import Path


class BudgetExhausted(Exception):
    pass


class SqliteTokenBudget:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @contextmanager
    def _connection(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("CREATE TABLE IF NOT EXISTS daily_budget (day TEXT PRIMARY KEY, spent INTEGER NOT NULL DEFAULT 0, reserved INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, day TEXT NOT NULL, amount INTEGER NOT NULL, state TEXT NOT NULL)")
        try:
            yield conn
        finally:
            conn.close()

    def reserve(self, day: str, amount: int, daily_limit: int) -> str:
        """Atomically claim estimated tokens before contacting a paid provider."""
        if amount <= 0 or daily_limit <= 0 or amount > daily_limit:
            raise ValueError("Invalid token reservation or daily limit")
        reservation_id = uuid.uuid4().hex
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("INSERT OR IGNORE INTO daily_budget(day) VALUES (?)", (day,))
                cursor = conn.execute(
                    "UPDATE daily_budget SET reserved=reserved+? WHERE day=? AND spent+reserved+?<=?",
                    (amount, day, amount, daily_limit),
                )
                if cursor.rowcount != 1:
                    raise BudgetExhausted("Daily AI budget unavailable")
                conn.execute("INSERT INTO reservations(id,day,amount,state) VALUES (?,?,?,'pending')", (reservation_id, day, amount))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return reservation_id

    def settle(self, reservation_id: str, actual_tokens: int) -> bool:
        """Consume the reservation once; unknown actual usage charges the full estimate."""
        if actual_tokens < 0:
            raise ValueError("Actual token usage cannot be negative")
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT day,amount,state FROM reservations WHERE id=?", (reservation_id,)).fetchone()
                if row is None or row[2] != "pending":
                    conn.execute("ROLLBACK")
                    return False
                day, reserved, _ = row
                # Never silently undercount if the provider reports more than estimated.
                charge = max(reserved, actual_tokens) if actual_tokens > reserved else actual_tokens
                conn.execute("UPDATE daily_budget SET reserved=reserved-?,spent=spent+? WHERE day=?", (reserved, charge, day))
                conn.execute("UPDATE reservations SET state='settled' WHERE id=?", (reservation_id,))
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def totals(self, day: str) -> tuple[int, int]:
        with self._connection() as conn:
            row = conn.execute("SELECT spent,reserved FROM daily_budget WHERE day=?", (day,)).fetchone()
            return (int(row[0]), int(row[1])) if row else (0, 0)
