"""IncrementalFeatures must reproduce compute_features() bar for bar."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PKG = Path(__file__).resolve().parents[1] / "playbooks" / "runeclaw-intraday-session-flow"
sys.path.insert(0, str(PKG))

from src import features  # noqa: E402
from src.params import PlaybookParams  # noqa: E402


def synthetic(n_days: int, seed: int, drop_some: bool) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-01 09:15", periods=n_days * 96, freq="15min", tz="UTC")
    rets = rng.normal(0, 0.002, len(idx))
    close = 50.0 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.001, len(idx))))
    low = close * (1 - np.abs(rng.normal(0, 0.001, len(idx))))
    open_ = np.roll(close, 1); open_[0] = close[0]
    vol = rng.lognormal(4.0, 0.5, len(idx))
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)
    if drop_some:  # simulate missing bars
        keep = np.ones(len(df), dtype=bool)
        keep[rng.choice(len(df), size=len(df) // 40, replace=False)] = False
        df = df[keep]
    return df


class IncrementalEqualsVectorized(unittest.TestCase):
    def _compare(self, df: pd.DataFrame) -> None:
        params = PlaybookParams()
        vec = features.compute_features(df, params)
        inc = features.IncrementalFeatures(params)
        rows = [inc.update(ts.to_pydatetime(), r.open, r.high, r.low, r.close, r.volume) for ts, r in zip(df.index, df.itertuples())]
        got = pd.DataFrame(rows, index=df.index)
        for col in features.FEATURE_COLUMNS:
            a, b = vec[col].to_numpy(dtype=float), got[col].to_numpy(dtype=float)
            same_nan = np.isnan(a) == np.isnan(b)
            self.assertTrue(same_nan.all(), f"{col}: NaN pattern differs at {np.where(~same_nan)[0][:5]}")
            mask = ~np.isnan(a)
            np.testing.assert_allclose(a[mask], b[mask], rtol=1e-9, atol=1e-9, err_msg=col)

    def test_contiguous(self) -> None:
        self._compare(synthetic(14, 3, drop_some=False))

    def test_with_gaps(self) -> None:
        self._compare(synthetic(14, 5, drop_some=True))


if __name__ == "__main__":
    unittest.main()
