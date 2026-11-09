"""Minimal stand-in for the sandbox-only `getagent` SDK so the live decision and
reconciliation code can be imported and exercised locally. Only the attributes
touched at import time or by the tested functions exist; nothing here talks to
a network."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd


def _prepare_frame(source: Any, datetime_index: str | None = None, rename_columns: dict | None = None) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source
    raise NotImplementedError("stub prepare_frame only accepts DataFrames")


backtest = SimpleNamespace(prepare_frame=_prepare_frame, run=None, generate_chart=lambda result: "")
data = SimpleNamespace(
    to_records=lambda payload: list(payload) if isinstance(payload, list) else [],
    crypto=SimpleNamespace(futures=SimpleNamespace(kline=None, ticker=None, funding_rate=None)),
)
runtime = SimpleNamespace(
    manifest={"strategy_config": {}},
    backtest_spec={},
    run_id="stub-run",
    evaluation_mode="live",
    is_historical=lambda: False,
    is_live=lambda: True,
    emit_signal=lambda **kwargs: kwargs,
    emit_signal_or_follow=lambda **kwargs: kwargs,
)
trade = SimpleNamespace(
    is_success=lambda result: bool(result),
    helpers=SimpleNamespace(),
    contract=SimpleNamespace(),
    account=SimpleNamespace(),
    market=SimpleNamespace(),
)
