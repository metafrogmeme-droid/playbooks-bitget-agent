"""Causal feature engineering shared by the replay and live paths.

Input: a 15-minute OHLCV DataFrame indexed by UTC bar *open* time with
columns ``open, high, low, close, volume`` (what ``backtest.prepare_frame``
returns for ``data.crypto.futures.kline``).

Output: the same frame plus the feature columns listed in ``FEATURE_COLUMNS``.
Every column only uses information available at that bar's close, so the
replay engine can read it row-by-row without look-ahead:

* ``vwap_session`` / ``vwap_sigma`` - session VWAP anchored at 00:00 UTC and the
  volume-weighted standard deviation of typical price around it.
* ``rsi``            - Wilder RSI on 15m closes.
* ``bias_slope_pct`` - percent change of the 1H EMA, using completed 1H bars only.
* ``atr4h_pct``      - Wilder ATR / close on completed 4H bars, in percent.
* ``vol_median_prev``- median volume of the previous N bars (current bar excluded).
* ``prior_high`` / ``prior_low`` - highest high / lowest low of the previous N bars.
* ``notional_24h``   - rolling 24h traded notional (sum of close*volume over 96 bars),
  the replay proxy for the exchange 24h quote volume gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .params import PlaybookParams

BAR_MINUTES = 15
BARS_PER_DAY = 24 * 60 // BAR_MINUTES

FEATURE_COLUMNS: tuple[str, ...] = (
    "vwap_session",
    "vwap_sigma",
    "rsi",
    "bias_slope_pct",
    "atr4h_pct",
    "vol_median_prev",
    "prior_high",
    "prior_low",
    "notional_24h",
)


# --------------------------------------------------------------------------- #
# indicator primitives
# --------------------------------------------------------------------------- #
def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    rsi[avg_gain.isna() | avg_loss.isna()] = np.nan
    return rsi


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def session_vwap(df: pd.DataFrame, anchor: str = "utc_day") -> tuple[pd.Series, pd.Series]:
    """Return (vwap, sigma) cumulative from the session anchor.

    ``anchor='utc_day'`` resets at 00:00 UTC, which matches the playbook's
    "flat before midnight" day definition.
    """
    if anchor != "utc_day":
        raise ValueError(f"unsupported vwap_anchor={anchor!r}; only 'utc_day' is implemented in v0.1")
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].astype(float)
    key = df.index.floor("1D")
    cum_v = vol.groupby(key).cumsum()
    cum_pv = (tp * vol).groupby(key).cumsum()
    cum_p2v = (tp * tp * vol).groupby(key).cumsum()
    safe_v = cum_v.replace(0.0, np.nan)
    vwap = cum_pv / safe_v
    var = (cum_p2v / safe_v) - vwap * vwap
    sigma = np.sqrt(var.clip(lower=0.0))
    return vwap, sigma


def _completed_htf_series(df15: pd.DataFrame, rule: str, fn) -> pd.Series:
    """Resample 15m bars to a higher timeframe, apply ``fn`` (Series -> Series),
    then map each value back to the 15m bars for which that HTF bar is already
    *closed* (HTF close time <= 15m bar close time).  Strictly causal."""
    htf = (
        df15[["open", "high", "low", "close", "volume"]]
        .resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )
    values = fn(htf)
    htf_close_time = htf.index + pd.Timedelta(rule)
    right = pd.DataFrame({"close_time": htf_close_time.values, "value": values.values}).sort_values("close_time")
    left = pd.DataFrame(
        {"close_time": (df15.index + pd.Timedelta(minutes=BAR_MINUTES)).values, "_i": np.arange(len(df15))}
    ).sort_values("close_time")
    merged = pd.merge_asof(left, right, on="close_time", direction="backward")
    merged = merged.sort_values("_i")
    return pd.Series(merged["value"].values, index=df15.index)


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def compute_features(df15: pd.DataFrame, params: PlaybookParams) -> pd.DataFrame:
    df = df15.copy()
    df.columns = [str(c).lower() for c in df.columns]
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"15m frame missing columns {sorted(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("15m frame must be indexed by a DatetimeIndex (UTC bar open time)")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)

    vwap, sigma = session_vwap(df, params.vwap_anchor)
    df["vwap_session"] = vwap
    df["vwap_sigma"] = sigma
    df["rsi"] = wilder_rsi(df["close"], params.rsi_period)

    ema_period = params.bias_ema_period
    df["bias_slope_pct"] = _completed_htf_series(
        df,
        "1h",
        lambda h: h["close"].ewm(span=ema_period, min_periods=ema_period, adjust=False).mean().pct_change() * 100.0,
    )
    atr_period = params.regime_atr_period
    df["atr4h_pct"] = _completed_htf_series(
        df,
        "4h",
        lambda h: wilder_atr(h["high"], h["low"], h["close"], atr_period) / h["close"] * 100.0,
    )

    n_vol = params.volume_median_bars
    n_brk = params.breakout_lookback_bars
    df["vol_median_prev"] = df["volume"].shift(1).rolling(n_vol, min_periods=n_vol).median()
    df["prior_high"] = df["high"].shift(1).rolling(n_brk, min_periods=n_brk).max()
    df["prior_low"] = df["low"].shift(1).rolling(n_brk, min_periods=n_brk).min()
    df["notional_24h"] = (df["close"] * df["volume"]).rolling(BARS_PER_DAY, min_periods=BARS_PER_DAY).sum()
    return df


@dataclass(frozen=True)
class SignalCandidate:
    kind: str            # "A" (VWAP reversion) or "B" (volume-spike breakout)
    side: str            # "long" | "short"
    limit_price: float   # entry limit
    stop_price: float    # initial protective stop
    target_price: float  # initial target (A: VWAP, B: entry + target_r * R)
    expiry_minutes: int
    r_distance: float    # |limit_price - stop_price|
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "side": self.side,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "expiry_minutes": self.expiry_minutes,
            "r_distance": self.r_distance,
            "reasons": list(self.reasons),
        }


def _finite(*values: Any) -> bool:
    try:
        return all(v is not None and np.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


def regime_ok(row: Any, params: PlaybookParams) -> tuple[bool, str]:
    atr_pct = row["atr4h_pct"] if "atr4h_pct" in row else None
    if not _finite(atr_pct):
        return False, "regime_unavailable"
    if atr_pct < params.regime_atr_pct_min:
        return False, "regime_chop"
    if atr_pct > params.regime_atr_pct_max:
        return False, "regime_event_risk"
    return True, "regime_ok"


def bias_state(row: Any, params: PlaybookParams) -> str:
    """'up' | 'down' | 'flat' | 'unknown' from the completed-1H EMA slope."""
    slope = row["bias_slope_pct"] if "bias_slope_pct" in row else None
    if not _finite(slope):
        return "unknown"
    if abs(slope) < params.bias_flat_slope_pct:
        return "flat"
    return "up" if slope > 0 else "down"


def detect_signals(row: Any, params: PlaybookParams) -> list[SignalCandidate]:
    """Pure rule evaluation on one completed 15m bar (a feature row).

    Does NOT apply session, regime, risk-budget, or liquidity gates; callers
    do that (see ``risk.py``).  Returns zero, one or two candidates (A and B
    can both fire; the caller picks by priority).
    """
    out: list[SignalCandidate] = []
    close = float(row["close"])
    high = float(row["high"])
    low = float(row["low"])
    bias = bias_state(row, params)

    # ---- Signal A: VWAP reversion (counter-trend) -------------------------
    if params.enable_signal_a and _finite(row["vwap_session"], row["vwap_sigma"], row["rsi"]) and float(row["vwap_sigma"]) > 0:
        vwap = float(row["vwap_session"])
        sig = float(row["vwap_sigma"])
        rsi = float(row["rsi"])
        upper_trig = vwap + params.vwap_trigger_sigma * sig
        lower_trig = vwap - params.vwap_trigger_sigma * sig
        if close >= upper_trig and rsi > params.rsi_overbought and bias in ("flat", "down"):
            limit = vwap + params.vwap_limit_sigma * sig
            stop = vwap + params.vwap_stop_sigma * sig
            out.append(
                SignalCandidate(
                    kind="A", side="short", limit_price=limit, stop_price=stop, target_price=vwap,
                    expiry_minutes=params.signal_a_expiry_minutes, r_distance=abs(limit - stop),
                    reasons=(f"close>=vwap+{params.vwap_trigger_sigma}s", f"rsi>{params.rsi_overbought}", f"bias={bias}"),
                )
            )
        elif close <= lower_trig and rsi < params.rsi_oversold and bias in ("flat", "up"):
            limit = vwap - params.vwap_limit_sigma * sig
            stop = vwap - params.vwap_stop_sigma * sig
            out.append(
                SignalCandidate(
                    kind="A", side="long", limit_price=limit, stop_price=stop, target_price=vwap,
                    expiry_minutes=params.signal_a_expiry_minutes, r_distance=abs(limit - stop),
                    reasons=(f"close<=vwap-{params.vwap_trigger_sigma}s", f"rsi<{params.rsi_oversold}", f"bias={bias}"),
                )
            )

    # ---- Signal B: volume-spike breakout (trend) ---------------------------
    if params.enable_signal_b and _finite(row["vol_median_prev"], row["prior_high"], row["prior_low"]) and float(row["vol_median_prev"]) > 0:
        vol = float(row["volume"])
        spike = vol >= params.volume_spike_mult * float(row["vol_median_prev"])
        mode = params.signal_b_entry_mode
        if mode not in ("close", "midpoint"):
            raise ValueError(f"unsupported signal_b_entry_mode={mode!r}; use 'close' or 'midpoint'")
        # Entry limit price: the breakout bar's close (v0.8+) or its midpoint (v0.1-v0.6).
        # The stop stays at the bar's opposite extreme, so R is measured from the entry.
        entry = close if mode == "close" else (high + low) / 2.0
        entry_tag = f"entry={mode}"
        if spike and close > float(row["prior_high"]) and bias == "up":
            r = entry - low
            if r > 0:
                out.append(
                    SignalCandidate(
                        kind="B", side="long", limit_price=entry, stop_price=low,
                        target_price=entry + params.signal_b_target_r * r,
                        expiry_minutes=params.signal_b_expiry_minutes, r_distance=r,
                        reasons=(f"vol>={params.volume_spike_mult}x_median", "close>prior_high", "bias=up", entry_tag),
                    )
                )
        elif spike and close < float(row["prior_low"]) and bias == "down":
            r = high - entry
            if r > 0:
                out.append(
                    SignalCandidate(
                        kind="B", side="short", limit_price=entry, stop_price=high,
                        target_price=entry - params.signal_b_target_r * r,
                        expiry_minutes=params.signal_b_expiry_minutes, r_distance=r,
                        reasons=(f"vol>={params.volume_spike_mult}x_median", "close<prior_low", "bias=down", entry_tag),
                    )
                )
    return out


def latest_feature_row(df: pd.DataFrame) -> dict[str, Any]:
    """Last completed bar as a plain dict (for live decisions / logging)."""
    row = df.iloc[-1]
    out = {k: (None if (isinstance(v, float) and not np.isfinite(v)) else v) for k, v in row.to_dict().items()}
    out["bar_open_ts"] = df.index[-1].isoformat()
    return out


# --------------------------------------------------------------------------- #
# incremental twin of compute_features (used bar-by-bar inside the Nautilus
# strategy so the replay never depends on injected columns).  Unit tests assert
# it reproduces compute_features() exactly on the same bars.
# --------------------------------------------------------------------------- #
from collections import deque  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


class _Wilder:
    """ewm(alpha=1/period, adjust=False, min_periods=period) on a stream."""

    def __init__(self, period: int) -> None:
        self.alpha = 1.0 / period
        self.period = period
        self.value: float | None = None
        self.count = 0

    def update(self, x: float) -> float | None:
        if x != x:  # NaN input is skipped (pandas ignore_na=False behaviour on a leading NaN)
            return None
        self.value = x if self.value is None else self.alpha * x + (1.0 - self.alpha) * self.value
        self.count += 1
        return self.value if self.count >= self.period else None


class _Ema:
    """ewm(span=period, adjust=False, min_periods=period) on a stream."""

    def __init__(self, period: int) -> None:
        self.alpha = 2.0 / (period + 1.0)
        self.period = period
        self.value: float | None = None
        self.count = 0

    def update(self, x: float) -> float | None:
        self.value = x if self.value is None else self.alpha * x + (1.0 - self.alpha) * self.value
        self.count += 1
        return self.value if self.count >= self.period else None


class _HtfAggregator:
    """Builds completed higher-timeframe bars from 15m bars (bins aligned to 00:00 UTC)."""

    def __init__(self, minutes: int) -> None:
        self.period = timedelta(minutes=minutes)
        self.bucket_start: datetime | None = None
        self.o = self.h = self.l = self.c = None
        self.v = 0.0

    def _floor(self, ts: datetime) -> datetime:
        day = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        n = int((ts - day) // self.period)
        return day + n * self.period

    def update(self, open_ts: datetime, o: float, h: float, l: float, c: float, v: float) -> tuple | None:
        """Feed one 15m bar; return a completed (o,h,l,c,v) HTF bar when one closes, else None."""
        completed = None
        bucket = self._floor(open_ts)
        if self.bucket_start is not None and bucket != self.bucket_start:
            completed = (self.o, self.h, self.l, self.c, self.v)
            self.bucket_start = None
        if self.bucket_start is None:
            self.bucket_start, self.o, self.h, self.l, self.c, self.v = bucket, o, h, l, c, v
        else:
            self.h, self.l, self.c, self.v = max(self.h, h), min(self.l, l), c, self.v + v
        if open_ts + timedelta(minutes=BAR_MINUTES) >= bucket + self.period:
            closing = (self.o, self.h, self.l, self.c, self.v)
            self.bucket_start = None
            # a bar can close the previous bucket and the current one only if bars are missing;
            # return the most recent closed bar, the earlier one is returned via `pending`.
            if completed is not None:
                self.pending = completed
            return closing
        return completed


class IncrementalFeatures:
    """Streaming equivalent of compute_features() for one instrument."""

    def __init__(self, params: PlaybookParams) -> None:
        self.p = params
        self.day: datetime | None = None
        self.cum_v = self.cum_pv = self.cum_p2v = 0.0
        self.prev_close: float | None = None
        self.gain = _Wilder(params.rsi_period)
        self.loss = _Wilder(params.rsi_period)
        self.h1 = _HtfAggregator(60)
        self.ema = _Ema(params.bias_ema_period)
        self.ema_prev: float | None = None
        self.ema_now: float | None = None
        self.h4 = _HtfAggregator(240)
        self.atr = _Wilder(params.regime_atr_period)
        self.atr_pct: float | None = None
        self.h4_prev_close: float | None = None
        self.vols: deque = deque(maxlen=params.volume_median_bars)
        self.highs: deque = deque(maxlen=params.breakout_lookback_bars)
        self.lows: deque = deque(maxlen=params.breakout_lookback_bars)
        self.notional: deque = deque(maxlen=BARS_PER_DAY)
        self.notional_sum = 0.0

    def _on_h1(self, bar: tuple) -> None:
        value = self.ema.update(bar[3])
        self.ema_prev, self.ema_now = self.ema_now, value

    def _on_h4(self, bar: tuple) -> None:
        o, h, l, c, _ = bar
        if self.h4_prev_close is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - self.h4_prev_close), abs(l - self.h4_prev_close))
        self.h4_prev_close = c
        atr = self.atr.update(tr)
        self.atr_pct = (atr / c * 100.0) if atr is not None and c else None

    def update(self, open_ts: datetime, o: float, h: float, l: float, c: float, v: float) -> dict[str, Any]:
        if open_ts.tzinfo is None:
            open_ts = open_ts.replace(tzinfo=timezone.utc)
        nan = float("nan")
        # previous-bar windows first (current bar excluded)
        vol_median_prev = float(np.median(list(self.vols))) if len(self.vols) == self.vols.maxlen else nan
        prior_high = max(self.highs) if len(self.highs) == self.highs.maxlen else nan
        prior_low = min(self.lows) if len(self.lows) == self.lows.maxlen else nan

        # session VWAP / sigma
        day = open_ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if day != self.day:
            self.day, self.cum_v, self.cum_pv, self.cum_p2v = day, 0.0, 0.0, 0.0
        tp = (h + l + c) / 3.0
        self.cum_v += v
        self.cum_pv += tp * v
        self.cum_p2v += tp * tp * v
        if self.cum_v > 0:
            vwap = self.cum_pv / self.cum_v
            sigma = float(np.sqrt(max(self.cum_p2v / self.cum_v - vwap * vwap, 0.0)))
        else:
            vwap, sigma = nan, nan

        # RSI
        rsi = nan
        if self.prev_close is not None:
            delta = c - self.prev_close
            g = self.gain.update(max(delta, 0.0))
            lo = self.loss.update(max(-delta, 0.0))
            if g is not None and lo is not None:
                rsi = 100.0 if lo == 0.0 else 100.0 - 100.0 / (1.0 + g / lo)
        self.prev_close = c

        # higher timeframes (completed bars only)
        done = self.h1.update(open_ts, o, h, l, c, v)
        if done is not None:
            pend = getattr(self.h1, "pending", None)
            if pend is not None:
                self._on_h1(pend)
                self.h1.pending = None
            self._on_h1(done)
        slope = nan
        if self.ema_now is not None and self.ema_prev is not None and self.ema_prev != 0:
            slope = (self.ema_now - self.ema_prev) / self.ema_prev * 100.0
        done4 = self.h4.update(open_ts, o, h, l, c, v)
        if done4 is not None:
            pend = getattr(self.h4, "pending", None)
            if pend is not None:
                self._on_h4(pend)
                self.h4.pending = None
            self._on_h4(done4)
        atr_pct = self.atr_pct if self.atr_pct is not None else nan

        # rolling 24h notional (current bar included)
        self.notional.append(c * v)
        self.notional_sum = float(sum(self.notional))
        notional_24h = self.notional_sum if len(self.notional) == self.notional.maxlen else nan

        row = {
            "open": o, "high": h, "low": l, "close": c, "volume": v,
            "vwap_session": vwap, "vwap_sigma": sigma, "rsi": rsi, "bias_slope_pct": slope,
            "atr4h_pct": atr_pct, "vol_median_prev": vol_median_prev, "prior_high": prior_high,
            "prior_low": prior_low, "notional_24h": notional_24h,
        }
        # push current bar into the "previous" windows for the next bar
        self.vols.append(v)
        self.highs.append(h)
        self.lows.append(l)
        return row
