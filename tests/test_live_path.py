"""Exercise main_live.decide and journal.reconcile with a stubbed SDK.

Run from the repo root:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PKG = HERE.parents[0] / "playbooks" / "runeclaw-intraday-session-flow"
sys.path.insert(0, str(HERE / "stubs"))
sys.path.insert(0, str(PKG))

from src import features, journal, main_live  # noqa: E402
from src.params import PlaybookParams  # noqa: E402
from src.risk import DailyLedger  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 1, 6, 8, 0, tzinfo=UTC)  # inside EU window, not a funding window


def frame_with_last_row(**overrides) -> pd.DataFrame:
    """Build a feature frame whose last row is forced to the given values."""
    idx = pd.date_range("2026-01-01", periods=96 * 5, freq="15min", tz="UTC")
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 0.05, len(idx)))
    df = pd.DataFrame({"open": close, "high": close + 0.1, "low": close - 0.1, "close": close, "volume": 10.0}, index=idx)
    df = features.compute_features(df, PlaybookParams())
    for key, value in overrides.items():
        df.iloc[-1, df.columns.get_loc(key)] = value
    return df


def ticker(volume=5e8, spread=1.0):
    return {"quote_volume_24h": volume, "spread_bps": spread, "last": 100.0}


class DecideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.params = PlaybookParams()
        self.ledger = DailyLedger()
        self.ledger.roll(NOW)
        self.state = journal.empty_state()

    def test_open_signal_a_short(self) -> None:
        feats = frame_with_last_row(close=110.0, high=110.5, low=109.0, vwap_session=100.0, vwap_sigma=5.0, rsi=75.0,
                                    bias_slope_pct=0.0, atr4h_pct=1.2, vol_median_prev=10.0, prior_high=200.0, prior_low=0.0)
        d = main_live.decide("BTCUSDT", feats, "ok", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual((d["action"], d["intent"]), ("short", "open"))
        self.assertEqual(d["candidate"]["kind"], "A")
        self.assertAlmostEqual(d["candidate"]["limit_price"], 105.0)
        self.assertTrue(d["signal_id"].startswith("RC-BTCUSDT-A-"))
        self.assertEqual(d["size"]["risk_usdt"], 5.0)
        self.assertEqual(d["metrics"]["sizing_ok"], True)

    def test_regime_blocks(self) -> None:
        feats = frame_with_last_row(close=110.0, vwap_session=100.0, vwap_sigma=5.0, rsi=75.0, bias_slope_pct=0.0, atr4h_pct=0.2)
        d = main_live.decide("BTCUSDT", feats, "ok", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual((d["action"], d["reason"]), ("hold", "regime_chop"))

    def test_spread_and_volume_gates(self) -> None:
        feats = frame_with_last_row(close=110.0, vwap_session=100.0, vwap_sigma=5.0, rsi=75.0, bias_slope_pct=0.0, atr4h_pct=1.2)
        d = main_live.decide("BTCUSDT", feats, "ok", ticker(spread=5.0), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "spread_above_max")
        d = main_live.decide("BTCUSDT", feats, "ok", ticker(volume=1e8), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "volume_below_min")

    def test_outside_session(self) -> None:
        feats = frame_with_last_row(close=110.0, vwap_session=100.0, vwap_sigma=5.0, rsi=75.0, bias_slope_pct=0.0, atr4h_pct=1.2)
        noon = NOW.replace(hour=12)
        d = main_live.decide("BTCUSDT", feats, "ok", ticker(), None, noon, self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "outside_session")

    def test_stale_feed_holds(self) -> None:
        d = main_live.decide("BTCUSDT", None, "stale_feed:45m", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual(d["action"], "hold")
        self.assertIn("stale_feed", d["reason"])

    def test_pending_expiry(self) -> None:
        self.state["pending"]["ETHUSDT"] = {"signal_id": "RC-ETHUSDT-B-x", "side": "long", "order_id": "1",
                                            "expires_at": (NOW - timedelta(minutes=1)).isoformat(), "limit_price": 1.0}
        d = main_live.decide("ETHUSDT", None, "ok", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual((d["action"], d["intent"]), ("close", "cancel_expired"))
        self.state["pending"]["ETHUSDT"]["expires_at"] = (NOW + timedelta(minutes=10)).isoformat()
        d = main_live.decide("ETHUSDT", None, "ok", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "pending_entry_active")

    def _open(self, kind="B", side="long", opened_minutes_ago=30):
        self.state["open"]["SOLUSDT"] = {
            "signal_id": f"RC-SOLUSDT-{kind}-x", "kind": kind, "side": side, "qty": 10.0, "entry_price": 100.0,
            "stop": 99.0 if side == "long" else 101.0, "target": 102.0 if side == "long" else 98.0, "r_distance": 1.0,
            "opened_at": (NOW - timedelta(minutes=opened_minutes_ago)).isoformat(), "best_excursion": 100.0, "entry_order_id": "9",
        }

    def test_time_stop(self) -> None:
        self._open(opened_minutes_ago=121)
        d = main_live.decide("SOLUSDT", None, "ok", ticker(), 0.0001, NOW, self.params, self.ledger, self.state)
        self.assertEqual((d["action"], d["intent"], d["reason"]), ("close", "flatten", "time_stop"))

    def test_funding_direction_aware(self) -> None:
        self._open(side="long")
        pre_funding = NOW.replace(hour=7, minute=45)
        d = main_live.decide("SOLUSDT", None, "ok", ticker(), 0.0001, pre_funding, self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "funding_window")                 # long pays positive funding
        d = main_live.decide("SOLUSDT", None, "ok", ticker(), -0.0001, pre_funding, self.params, self.ledger, self.state)
        self.assertNotEqual(d.get("intent"), "flatten")                  # long receives negative funding -> keep
        d = main_live.decide("SOLUSDT", None, "ok", ticker(), None, pre_funding, self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "funding_window_rate_unknown")     # unknown -> conservative flatten

    def test_eod_flatten(self) -> None:
        self._open()
        d = main_live.decide("SOLUSDT", None, "ok", ticker(), None, NOW.replace(hour=23, minute=45), self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "eod_flatten")

    def test_daily_cap_flatten(self) -> None:
        self._open()
        self.ledger.record_pnl(-20.0, self.params)
        d = main_live.decide("SOLUSDT", None, "ok", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "daily_loss_cap")

    def test_manage_trailing_stop(self) -> None:
        self._open(kind="B", side="long")
        feats = frame_with_last_row(high=102.0, low=101.0, close=101.5, atr4h_pct=1.2)
        d = main_live.decide("SOLUSDT", feats, "ok", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual((d["action"], d["intent"]), ("long", "manage"))
        self.assertAlmostEqual(d["new_stop"], 101.0)      # best 102 - 1R
        self.assertAlmostEqual(d["best_excursion"], 102.0)

    def test_manage_vwap_target(self) -> None:
        self._open(kind="A", side="short")
        feats = frame_with_last_row(vwap_session=97.5, atr4h_pct=1.2)
        d = main_live.decide("SOLUSDT", feats, "ok", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual(d["intent"], "manage")
        self.assertAlmostEqual(d["new_target"], 97.5)

    def test_max_concurrent_counts_pending(self) -> None:
        self.state["pending"]["ETHUSDT"] = {"signal_id": "x", "side": "long", "order_id": "1",
                                            "expires_at": (NOW + timedelta(minutes=10)).isoformat(), "limit_price": 1.0}
        self._open()
        feats = frame_with_last_row(close=110.0, vwap_session=100.0, vwap_sigma=5.0, rsi=75.0, bias_slope_pct=0.0, atr4h_pct=1.2)
        d = main_live.decide("BTCUSDT", feats, "ok", ticker(), None, NOW, self.params, self.ledger, self.state)
        self.assertEqual(d["reason"], "max_concurrent")


class ReconcileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.params = PlaybookParams()
        self.ledger = DailyLedger()
        self.ledger.roll(NOW)
        self.state = journal.empty_state()
        self.journal = journal.Journal()

    def test_pending_filled(self) -> None:
        self.state["pending"]["BTCUSDT"] = {"signal_id": "RC-BTCUSDT-A-x", "kind": "A", "side": "short", "order_id": "42",
                                            "limit_price": 105.0, "stop": 110.0, "target": 100.0, "r_distance": 5.0}
        positions = [{"symbol": "BTCUSDT", "holdSide": "short", "total": "0.05", "openPriceAvg": "104.9"}]
        flags = journal.reconcile(state=self.state, pos_records=positions, pending_payload={"data": []},
                                  fills_lookup=lambda s, o: [{"orderId": o, "priceAvg": "104.95"}], now=NOW,
                                  params=self.params, ledger=self.ledger, journal=self.journal)
        self.assertEqual(flags, [])
        self.assertIn("BTCUSDT", self.state["open"])
        self.assertAlmostEqual(self.state["open"]["BTCUSDT"]["entry_price"], 104.95)
        self.assertEqual(self.ledger.trades_by_symbol["BTCUSDT"], 1)
        self.assertEqual([r["event"] for r in self.journal.rows], ["entry_filled"])

    def test_pending_vanished_without_position(self) -> None:
        self.state["pending"]["BTCUSDT"] = {"signal_id": "x", "kind": "A", "side": "short", "order_id": "42",
                                            "limit_price": 105.0, "stop": 110.0, "target": 100.0, "r_distance": 5.0}
        journal.reconcile(state=self.state, pos_records=[], pending_payload={"data": []}, fills_lookup=lambda s, o: [],
                          now=NOW, params=self.params, ledger=self.ledger, journal=self.journal)
        self.assertEqual(self.state["pending"], {})
        self.assertEqual(self.journal.rows[0]["event"], "entry_expired")

    def test_open_closed_on_exchange_infers_reason(self) -> None:
        self.state["open"]["ETHUSDT"] = {"signal_id": "x", "kind": "B", "side": "long", "qty": 1.0, "entry_price": 100.0,
                                         "stop": 99.0, "target": 102.0, "r_distance": 1.0, "opened_at": NOW.isoformat(),
                                         "entry_order_id": "7"}
        journal.reconcile(state=self.state, pos_records=[], pending_payload={"data": []},
                          fills_lookup=lambda s, o: [{"price": "98.95"}], now=NOW, params=self.params,
                          ledger=self.ledger, journal=self.journal)
        row = self.journal.rows[-1]
        self.assertEqual((row["event"], row["exit_reason"]), ("exit", "stop_hit"))
        self.assertAlmostEqual(self.ledger.realized_pnl_usdt, -1.05)
        self.assertEqual(self.state["open"], {})

    def test_untracked_position_flags(self) -> None:
        positions = [{"symbol": "SOLUSDT", "holdSide": "long", "total": "3"}]
        flags = journal.reconcile(state=self.state, pos_records=positions, pending_payload={"data": []},
                                  fills_lookup=lambda s, o: [], now=NOW, params=self.params, ledger=self.ledger,
                                  journal=self.journal)
        self.assertEqual(flags[0]["type"], "untracked_position")
        self.assertEqual(self.state["reconcile_flags"], flags)

    def test_extract_order_id(self) -> None:
        self.assertEqual(journal.extract_order_id({"data": {"orderId": "123"}}), "123")
        self.assertEqual(journal.extract_order_id({"result": [{"order_id": 9}]}), "9")
        self.assertEqual(journal.extract_order_id(None), "")
        self.assertEqual(journal.pending_order_ids({"data": {"entrustedList": [{"orderId": "a", "symbol": "BTCUSDT"}]}}, "BTCUSDT"), {"a"})


if __name__ == "__main__":
    unittest.main()
