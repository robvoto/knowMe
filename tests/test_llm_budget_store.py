import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.app.llm_budget_store import BudgetExhausted, SqliteTokenBudget


class SqliteTokenBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "usage.sqlite3"
        self.store = SqliteTokenBudget(self.path)

    def test_reservation_is_atomic_across_connections(self):
        def attempt(_):
            try:
                return self.store.reserve("2026-10-19", 25, 100)
            except BudgetExhausted:
                return None

        with ThreadPoolExecutor(max_workers=12) as pool:
            reservations = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(r is not None for r in reservations), 4)
        self.assertEqual(self.store.totals("2026-10-19"), (0, 100))

    def test_settlement_is_idempotent_and_releases_unused_reservation(self):
        rid = self.store.reserve("2026-10-19", 60, 100)
        self.assertTrue(self.store.settle(rid, 18))
        self.assertFalse(self.store.settle(rid, 18))
        self.assertEqual(self.store.totals("2026-10-19"), (18, 0))

    def test_unsettled_budget_stays_reserved_after_reopening(self):
        self.store.reserve("2026-10-19", 90, 100)
        reopened = SqliteTokenBudget(self.path)
        with self.assertRaises(BudgetExhausted):
            reopened.reserve("2026-10-19", 11, 100)
        self.assertEqual(reopened.totals("2026-10-19"), (0, 90))

    def test_legacy_usage_import_is_idempotent_and_never_resets_spending(self):
        self.store.import_legacy_floor("2026-10-19", 80)
        self.store.import_legacy_floor("2026-10-19", 80)
        self.assertEqual(self.store.totals("2026-10-19"), (80, 0))
        with self.assertRaises(BudgetExhausted):
            self.store.reserve("2026-10-19", 21, 100)
        rid = self.store.reserve("2026-10-19", 20, 100)
        self.store.settle(rid, 20)
        self.store.import_legacy_floor("2026-10-19", 80)
        self.assertEqual(self.store.totals("2026-10-19"), (100, 0))
        with self.assertRaises(ValueError):
            self.store.import_legacy_floor("2026-10-19", -1)

    def test_provider_overuse_is_never_silently_discarded(self):
        rid = self.store.reserve("2026-10-19", 20, 100)
        self.store.settle(rid, 120)
        self.assertEqual(self.store.totals("2026-10-19"), (120, 0))
        with self.assertRaises(BudgetExhausted):
            self.store.reserve("2026-10-19", 1, 100)


if __name__ == "__main__":
    unittest.main()
