#!/usr/bin/env python3
"""Download public Bitget USDT-M market data for offline research. No API key.

Endpoints (public, unauthenticated):
  GET /api/v2/mix/market/history-candles   15m candles, 200 per request, paged backwards
  GET /api/v2/mix/market/history-fund-rate funding settlements (the venue serves ~90 days)

Usage:
  python3 research/fetch_data.py --start 2026-02-07T00:00 --end 2026-11-09T17:15
Writes research/data/<SYMBOL>_15m.csv and research/data/<SYMBOL>_funding.csv
(research/data/ is git-ignored; rerun this script to rebuild it).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.bitget.com/api/v2/mix/market"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
BAR_MS = 15 * 60 * 1000
OUT = Path(__file__).resolve().parent / "data"


def _get(url: str, retries: int = 5) -> dict:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "offline-research"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            if payload.get("code") == "00000":
                return payload
            last = RuntimeError(f"{payload.get('code')} {payload.get('msg')}")
        except Exception as exc:  # noqa: BLE001 - retry any transport error
            last = exc
        time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET failed after {retries} tries: {url}: {last}")


def _ms(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp() * 1000)


def fetch_candles(symbol: str, start_ms: int, end_ms: int) -> list[list[str]]:
    """Closed 15m bars with open time in [start_ms, end_ms), oldest first."""
    rows: dict[int, list[str]] = {}
    cursor = end_ms
    while cursor > start_ms:
        data = _get(f"{BASE}/history-candles?symbol={symbol}&productType=USDT-FUTURES&granularity=15m&endTime={cursor}&limit=200")["data"]
        if not data:
            break
        for r in data:
            ts = int(r[0])
            if start_ms <= ts < end_ms:
                rows[ts] = r
        oldest = min(int(r[0]) for r in data)
        if oldest >= cursor:
            break
        cursor = oldest
        time.sleep(0.08)
    return [rows[k] for k in sorted(rows)]


def fetch_funding(symbol: str) -> list[tuple[int, str]]:
    out: dict[int, str] = {}
    for page in range(1, 20):
        data = _get(f"{BASE}/history-fund-rate?symbol={symbol}&productType=USDT-FUTURES&pageSize=100&pageNo={page}")["data"]
        if not data:
            break
        for r in data:
            out[int(r["fundingTime"])] = r["fundingRate"]
        time.sleep(0.08)
    return sorted(out.items())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="UTC, e.g. 2026-02-07T00:00")
    ap.add_argument("--end", required=True, help="UTC, exclusive, e.g. 2026-11-09T17:15")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    start_ms, end_ms = _ms(args.start), _ms(args.end)
    for symbol in SYMBOLS:
        bars = fetch_candles(symbol, start_ms, end_ms)
        lines = ["time_ms,open,high,low,close,volume,quote_volume"] + [",".join(r[:7]) for r in bars]
        (OUT / f"{symbol}_15m.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        expected = (end_ms - start_ms) // BAR_MS
        funding = fetch_funding(symbol)
        (OUT / f"{symbol}_funding.csv").write_text(
            "time_ms,funding_rate\n" + "\n".join(f"{t},{r}" for t, r in funding) + "\n", encoding="utf-8")
        first = datetime.fromtimestamp(funding[0][0] / 1000, timezone.utc).isoformat() if funding else "-"
        print(f"{symbol}: {len(bars)} bars of {expected} expected; funding rows {len(funding)} from {first}", flush=True)


if __name__ == "__main__":
    main()
