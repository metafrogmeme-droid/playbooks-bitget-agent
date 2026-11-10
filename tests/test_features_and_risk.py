"""Local unit tests for the pure modules (no getagent / nautilus needed).

Run from the repo root:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PKG = Path(__file__).resolve().parents[1] / "playbooks" / "runeclaw-intraday-session-flow"
sys.path.insert(0, str(PKG))

from src import features, risk  # noqa: E402
from src.params import PlaybookParams  # noqa: E402

UTC = timezone.utc


def synthetic_15m(n_days: int = 12, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n_days * 96, freq="15min", tz="UTC")
    rets = rng.normal(0, 0.0015, len(idx))
    close = 100.0 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.0008, len(idx))))
    low = close * (1 - np.abs(rng.normal(0, 0.0008, len(idx))))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    vol = rng.lognormal(mean=5.0, sigma=0.3, size=len(idx))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


class FeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.params = PlaybookParams(enable_signal_a=True)  # Signal A tests exercise the rule even while v0.4 ships it off
        self.df = features.compute_features(synthetic_15m(), self.params)

    def test_columns_present(self) -> None:
        for col in features.FEATURE_COLUMNS:
            self.assertIn(col, self.df.columns)

    def test_vwap_resets_each_utc_day(self) -> None:
        first_bars = self.df[self.df.index.strftime("%H:%M") == "00:00"]
        tp = (first_bars["high"] + first_bars["low"] + first_bars["close"]) / 3
        np.testing.assert_allclose(first_bars["vwap_session"].values, tp.values, rtol=1e-9)
        self.assertTrue((first_bars["vwap_sigma"].abs() < 1e-6).all())

    def test_htf_features_are_causal(self) -> None:
        # The 1H slope for the 15m bar closing at 01:00 must use hourly bars up to 00:00-01:00 only;
        # bars 01:00, 01:15, 01:30 must share the same value as the 00:45 bar (no newer completed hour).
        day = self.df.loc["2026-01-10"]
        v_0045 = day.loc["2026-01-10 00:45"]["bias_slope_pct"]
        for t in ("01:00", "01:15", "01:30"):
            self.assertEqual(day.loc[f"2026-01-10 {t}"]["bias_slope_pct"], v_0045)
        self.assertNotEqual(day.loc["2026-01-10 01:45"]["bias_slope_pct"], v_0045)
        # 4H ATR: bars 04:00..07:30 share the value computed at the bar closing 04:00 (i.e. 03:45 open)
        v_0345 = day.loc["2026-01-10 03:45"]["atr4h_pct"]
        self.assertEqual(day.loc["2026-01-10 07:30"]["atr4h_pct"], v_0345)
        self.assertNotEqual(day.loc["2026-01-10 07:45"]["atr4h_pct"], v_0345)

    def test_prior_high_excludes_current_bar(self) -> None:
        i = 500
        window = self.df["high"].iloc[i - 20:i]
        self.assertAlmostEqual(self.df["prior_high"].iloc[i], window.max())
        self.assertAlmostEqual(self.df["vol_median_prev"].iloc[i], self.df["volume"].iloc[i - 20:i].median())

    def test_rsi_bounds(self) -> None:
        rsi = self.df["rsi"].dropna()
        self.assertTrue(((rsi >= 0) & (rsi <= 100)).all())

    def test_signal_a_short_fires(self) -> None:
        row = {
            "close": 110.0, "high": 110.5, "low": 109.0, "volume": 1.0,
            "vwap_session": 100.0, "vwap_sigma": 5.0, "rsi": 75.0, "bias_slope_pct": 0.0,
            "vol_median_prev": 10.0, "prior_high": 120.0, "prior_low": 90.0,
        }
        sigs = features.detect_signals(row, self.params)
        self.assertEqual(len(sigs), 1)
        s = sigs[0]
        self.assertEqual((s.kind, s.side), ("A", "short"))
        self.assertAlmostEqual(s.limit_price, 105.0)
        self.assertAlmostEqual(s.stop_price, 110.0)
        self.assertAlmostEqual(s.target_price, 100.0)
        self.assertEqual(s.expiry_minutes, 45)

    def test_signal_a_blocked_by_strong_bias(self) -> None:
        row = {
            "close": 110.0, "high": 110.5, "low": 109.0, "volume": 1.0,
            "vwap_session": 100.0, "vwap_sigma": 5.0, "rsi": 75.0, "bias_slope_pct": 0.5,  # strong up
            "vol_median_prev": 10.0, "prior_high": 120.0, "prior_low": 90.0,
        }
        self.assertEqual(features.detect_signals(row, self.params), [])

    def test_signal_b_long_enters_at_close(self) -> None:
        row = {
            "close": 121.0, "high": 122.0, "low": 118.0, "volume": 30.0,
            "vwap_session": 100.0, "vwap_sigma": 5.0, "rsi": 60.0, "bias_slope_pct": 0.2,
            "vol_median_prev": 10.0, "prior_high": 120.0, "prior_low": 90.0,
        }
        sigs = features.detect_signals(row, self.params)
        self.assertEqual([(s.kind, s.side) for s in sigs], [("B", "long")])
        s = sigs[0]
        self.assertAlmostEqual(s.limit_price, 121.0)   # breakout bar close (v0.8)
        self.assertAlmostEqual(s.stop_price, 118.0)    # opposite extreme, unchanged
        self.assertAlmostEqual(s.r_distance, 3.0)
        self.assertAlmostEqual(s.target_price, 127.0)  # 2R above the entry
        self.assertEqual(s.expiry_minutes, 30)

    def test_signal_b_short_enters_at_close(self) -> None:
        row = {
            "close": 89.0, "high": 92.0, "low": 88.0, "volume": 30.0,
            "vwap_session": 100.0, "vwap_sigma": 5.0, "rsi": 40.0, "bias_slope_pct": -0.2,
            "vol_median_prev": 10.0, "prior_high": 120.0, "prior_low": 90.0,
        }
        s = features.detect_signals(row, self.params)[0]
        self.assertEqual((s.kind, s.side), ("B", "short"))
        self.assertAlmostEqual(s.limit_price, 89.0)
        self.assertAlmostEqual(s.stop_price, 92.0)
        self.assertAlmostEqual(s.target_price, 83.0)

    def test_signal_b_midpoint_mode_reproduces_v05(self) -> None:
        row = {
            "close": 121.0, "high": 122.0, "low": 118.0, "volume": 30.0,
            "vwap_session": 100.0, "vwap_sigma": 5.0, "rsi": 60.0, "bias_slope_pct": 0.2,
            "vol_median_prev": 10.0, "prior_high": 120.0, "prior_low": 90.0,
        }
        p = PlaybookParams(signal_b_entry_mode="midpoint")
        s = features.detect_signals(row, p)[0]
        self.assertAlmostEqual(s.limit_price, 120.0)
        self.assertAlmostEqual(s.stop_price, 118.0)
        self.assertAlmostEqual(s.target_price, 124.0)  # 2R above mid, as in v0.5
        with self.assertRaises(ValueError):
            features.detect_signals(row, PlaybookParams(signal_b_entry_mode="market"))

    def test_signal_b_volume_threshold(self) -> None:
        row = {
            "close": 121.0, "high": 122.0, "low": 118.0, "volume": 24.0,   # 2.4x median: below 2.5x
            "vwap_session": 100.0, "vwap_sigma": 5.0, "rsi": 60.0, "bias_slope_pct": 0.2,
            "vol_median_prev": 10.0, "prior_high": 120.0, "prior_low": 90.0,
        }
        self.assertEqual(features.detect_signals(row, self.params), [])

    def test_regime_filter(self) -> None:
        self.assertEqual(features.regime_ok({"atr4h_pct": 0.3}, self.params), (False, "regime_chop"))
        self.assertEqual(features.regime_ok({"atr4h_pct": 3.5}, self.params), (False, "regime_event_risk"))
        self.assertEqual(features.regime_ok({"atr4h_pct": 1.2}, self.params), (True, "regime_ok"))
        self.assertEqual(features.regime_ok({"atr4h_pct": float("nan")}, self.params), (False, "regime_unavailable"))


class RiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.params = PlaybookParams()

    def test_sessions(self) -> None:
        self.assertTrue(risk.in_session(datetime(2026, 1, 5, 7, 0, tzinfo=UTC), self.params))
        self.assertTrue(risk.in_session(datetime(2026, 1, 5, 9, 59, tzinfo=UTC), self.params))
        self.assertFalse(risk.in_session(datetime(2026, 1, 5, 10, 0, tzinfo=UTC), self.params))
        self.assertTrue(risk.in_session(datetime(2026, 1, 5, 13, 30, tzinfo=UTC), self.params))
        self.assertFalse(risk.in_session(datetime(2026, 1, 5, 16, 30, tzinfo=UTC), self.params))
        self.assertFalse(risk.in_session(datetime(2026, 1, 5, 12, 0, tzinfo=UTC), self.params))

    def test_funding_window(self) -> None:
        p = self.params
        self.assertEqual(p.effective_funding_lead_minutes, 15)
        self.assertTrue(risk.funding_flatten_due(datetime(2026, 1, 5, 7, 45, tzinfo=UTC), p))
        self.assertFalse(risk.funding_flatten_due(datetime(2026, 1, 5, 7, 30, tzinfo=UTC), p))
        self.assertTrue(risk.funding_flatten_due(datetime(2026, 1, 5, 15, 50, tzinfo=UTC), p))
        self.assertTrue(risk.funding_flatten_due(datetime(2026, 1, 5, 23, 50, tzinfo=UTC), p))
        self.assertAlmostEqual(risk.minutes_to_next_funding(datetime(2026, 1, 5, 8, 0, tzinfo=UTC), p), 480.0)

    def test_pays_funding(self) -> None:
        self.assertTrue(risk.position_pays_funding("long", 0.0001))
        self.assertFalse(risk.position_pays_funding("long", -0.0001))
        self.assertTrue(risk.position_pays_funding("short", -0.0001))
        self.assertIsNone(risk.position_pays_funding("short", None))

    def test_eod_and_time_stop(self) -> None:
        p = self.params
        self.assertTrue(risk.eod_flatten_due(datetime(2026, 1, 5, 23, 45, tzinfo=UTC), p))
        self.assertFalse(risk.eod_flatten_due(datetime(2026, 1, 5, 23, 30, tzinfo=UTC), p))
        opened = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
        self.assertEqual(p.time_stop_minutes, 180)  # v0.5 default
        self.assertFalse(risk.time_stop_due(opened, datetime(2026, 1, 5, 10, 45, tzinfo=UTC), p))
        self.assertTrue(risk.time_stop_due(opened, datetime(2026, 1, 5, 11, 0, tzinfo=UTC), p))
        p120 = PlaybookParams(time_stop_minutes=120)
        self.assertTrue(risk.time_stop_due(opened, datetime(2026, 1, 5, 10, 0, tzinfo=UTC), p120))

    def test_sizing(self) -> None:
        p = self.params  # 1000 USDT budget, 0.5% risk = 5 USDT
        plan = risk.size_from_risk(limit_price=100.0, stop_price=99.0, params=p, size_step=0.001, min_qty=0.001)
        self.assertTrue(plan.ok)
        self.assertAlmostEqual(plan.qty, 5.0)
        self.assertAlmostEqual(plan.risk_usdt, 5.0)
        # tiny stop distance -> notional cap at margin_budget * leverage = 3000
        plan2 = risk.size_from_risk(limit_price=100.0, stop_price=99.99, params=p, size_step=0.001, min_qty=0.001)
        self.assertTrue(plan2.capped_by_margin)
        self.assertLessEqual(plan2.notional_usdt, 3000.0 + 1e-6)

    def test_daily_ledger(self) -> None:
        p = self.params
        ledger = risk.DailyLedger()
        now = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
        self.assertTrue(ledger.roll(now))
        for _ in range(3):
            ledger.record_entry("BTCUSDT")
        self.assertFalse(ledger.symbol_budget_left("BTCUSDT", p))
        self.assertTrue(ledger.symbol_budget_left("ETHUSDT", p))
        ledger.record_pnl(-16.0, p)  # cap is 15 USDT
        self.assertTrue(ledger.halted)
        self.assertTrue(ledger.roll(datetime(2026, 1, 6, 0, 0, tzinfo=UTC)))
        self.assertFalse(ledger.halted)

    def test_can_open_new_gates(self) -> None:
        p = self.params
        ledger = risk.DailyLedger()
        now = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
        ledger.roll(now)
        ok, why = risk.can_open_new(now, p, ledger, "BTCUSDT", 0, 0, False, 0, 5e8, 1.0)
        self.assertEqual((ok, why), (True, "ok"))
        self.assertEqual(risk.can_open_new(now, p, ledger, "BTCUSDT", 1, 1, False, 0, 5e8, 1.0)[1], "max_concurrent")
        self.assertEqual(risk.can_open_new(now, p, ledger, "BTCUSDT", 0, 0, False, 0, 1e8, 1.0)[1], "volume_below_min")
        self.assertEqual(risk.can_open_new(now, p, ledger, "BTCUSDT", 0, 0, False, 0, 5e8, 4.0)[1], "spread_above_max")
        self.assertEqual(risk.can_open_new(now, p, ledger, "BTCUSDT", 0, 0, False, 1, 5e8, 1.0)[1], "halted:reconcile_mismatch")
        at_funding = datetime(2026, 1, 5, 7, 45, tzinfo=UTC)
        self.assertEqual(risk.can_open_new(at_funding, p, ledger, "BTCUSDT", 0, 0, False, 0, 5e8, 1.0)[1], "pre_funding_window")

    def test_trail(self) -> None:
        p = self.params
        # long from 100 with R=1: no trail until MFE >= 1R
        self.assertIsNone(risk.trail_stop("long", 100.0, 100.8, 99.0, 1.0, p))
        self.assertAlmostEqual(risk.trail_stop("long", 100.0, 101.5, 99.0, 1.0, p), 100.5)
        self.assertIsNone(risk.trail_stop("long", 100.0, 101.5, 100.6, 1.0, p))
        self.assertAlmostEqual(risk.trail_stop("short", 100.0, 98.0, 101.0, 1.0, p), 99.0)


if __name__ == "__main__":
    unittest.main()


class FundingLookupTests(unittest.TestCase):
    def test_latest_rate_at_or_before_now(self) -> None:
        hist = [[1_000_000, 0.0001], [3_000_000, -0.0002], [2_000_000, 0.00005]]
        now = datetime.fromtimestamp(2_500, tz=UTC)
        self.assertAlmostEqual(risk.funding_rate_at(hist, now), 0.00005)
        self.assertAlmostEqual(risk.funding_rate_at(hist, datetime.fromtimestamp(3_000, tz=UTC)), -0.0002)
        self.assertIsNone(risk.funding_rate_at(hist, datetime.fromtimestamp(500, tz=UTC)))
        self.assertIsNone(risk.funding_rate_at(None, now))
        self.assertIsNone(risk.funding_rate_at([["x", "y"]], now))
