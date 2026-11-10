#!/usr/bin/env python3
"""Repository mirror of the GetAgent skill's static package validator.

It re-implements the rules documented in `@bitget-ai/getagent-skill`
(references/package-schema.md and scripts/validate.py, v0.6.4) that apply to a
`trade_strategy` / `follow_trade` / `backtest_support: full` package, plus two
repo-specific checks (manifest defaults == params.py, user_config_schema
defaults == strategy_config).  Run the official validator as well before upload.

Usage: python3 tools/check_package.py playbooks/runeclaw-intraday-session-flow
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REQUIRED_FILES = ["README.md", "manifest.yaml", "src/main.py"]
MANIFEST_REQUIRED = ["name", "display_name", "version", "description", "long_description", "market_type",
                     "trading_symbols", "decision_mode", "backtest_support", "runtime_profile", "follow_trade_supported"]
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
SYMBOL_TOKEN_RE = re.compile(r"\b[A-Z0-9]{2,20}(?:USDT|USDC|USD|BTC|ETH)\b")
I18N = ("en", "zh", "zh-tw", "es", "ja", "vi")
LOCAL_ONLY = {"tests", "notebooks", "research", "data", "backtest_results", "logs", "output", ".venv", "__pycache__", ".pytest_cache"}
ALLOWED_IMPORTS = {"getagent", "getclaw", "nautilus_trader", "pandas", "numpy", "json", "math", "datetime", "pathlib", "asyncio",
                   "typing", "dataclasses", "collections", "functools", "re", "decimal", "statistics", "itertools", "operator",
                   "copy", "enum", "abc", "numbers", "fractions", "__future__"}
BLOCKED_IMPORTS = {"requests", "httpx", "trade_sdk", "ccxt", "subprocess", "os", "sys", "importlib", "socket", "urllib", "http",
                   "ftplib", "smtplib", "shutil", "sqlalchemy", "redis", "pymongo", "fastapi", "flask", "telegram", "slack_sdk",
                   "discord", "multiprocessing", "csv"}
MUTATIONS = {"add_investment", "cancel_order", "change_leverage", "close_bot", "close_position", "create_bot", "limit_order",
             "market_buy", "market_sell", "modify_bot", "modify_grid_interval", "modify_limit_order", "modify_stop_loss",
             "modify_take_profit", "open_long_limit", "open_long_market", "open_short_limit", "open_short_market", "place_order",
             "transfer"}
TPSL_KW = {"symbol", "side", "leverage", "tp_trigger_price", "sl_trigger_price", "reference_price", "product_type"}
LD_SECTIONS = {
    "thesis": ("capture", "captures", "tries to", "thesis", "aim", "aims", "objective", "designed", "seeks", "intended", "goal",
               "approach", "built on", "assumption", "purpose"),
    "entry": ("enter", "enters", "entry", "entering", "opens", "go long", "go short", "going long", "going short", "long position",
              "short position"),
    "exit": ("exit", "exits", "close", "closes", "closing", "stop", "take profit", "take-profit", "stop-loss", "stop loss"),
    "tunables": ("parameter", "parameters", "tunable", "leverage", "margin", "configurable", "adjust", "adjusts", "tune",
                 "subscriber", "subscribers"),
    "risks": ("risk", "risks", "drawdown", "drawdowns", "lose money", "loses money", "lost money", "loss", "losses", "underperform",
              "underperforms", "unsuitable", "fails", "weakness", "worst", "warning"),
}
LD_FORBIDDEN = [
    (re.compile(r"\b(?:EMA|SMA|WMA|MA|RSI|MACD|ATR|VWAP|ADX|Stoch(?:astic)?|Bollinger|MFI|CCI|OBV|DMI|TRIX|KDJ)[\s_/-]*\d+", re.I), "indicator+period"),
    (re.compile(r"\b\d+(?:\.\d+)?[\s/-]*(?:bar|bars|candle|candles|period|periods|day|days|hour|hours|minute|minutes|week|weeks|second|seconds|tick|ticks)\b", re.I), "numeric lookback"),
    (re.compile(r"(?<![\w.])(?:>=|<=|>|<|==)\s*-?\d"), "comparison threshold"),
    (re.compile(r"\b\d+(?:\.\d+)?\s*%"), "percentage"),
    (re.compile(r"\b\d+(?:\.\d+)?\s*x\b", re.I), "multiplier"),
    (re.compile(r"\b\d+\s*:\s*\d+\b"), "ratio"),
]
CJK_RE = re.compile(r"[　-〿぀-ゟ゠-ヿ㐀-䶿一-鿿豈-﫿＀-￯]")


class Result:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def check_structure(pkg: Path, r: Result) -> None:
    for rel in REQUIRED_FILES:
        if not (pkg / rel).exists():
            r.error(f"missing required file {rel}")
    for child in pkg.iterdir():
        if child.name in LOCAL_ONLY:
            r.error(f"local-only path inside package: {child.name}")
    readme = pkg / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8").strip()
        if len(text) < 200:
            r.error("README.md shorter than 200 chars")
        for phrase in ("策略", "开仓", "平仓", "风险"):
            if phrase not in text:
                r.error(f"README.md missing section keyword {phrase}")


def check_long_description(ld: object, description: str, r: Result) -> None:
    if not isinstance(ld, str) or not ld.strip():
        r.error("long_description missing")
        return
    text = ld.strip()
    words = len(text.split())
    if words < 250 or words > 500:
        r.error(f"long_description word count {words} outside 250-500")
    elif not 300 <= words <= 400:
        r.warn(f"long_description word count {words} outside target 300-400")
    if CJK_RE.search(text):
        r.error("long_description must be English only")
    for label, kws in LD_SECTIONS.items():
        rx = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")\b", re.I)
        if not rx.search(text):
            r.error(f"long_description missing section coverage: {label}")
    for rx, why in LD_FORBIDDEN:
        m = rx.search(text)
        if m:
            r.error(f"long_description forbidden content {m.group(0)!r} ({why})")
    d = " ".join(description.lower().split())
    l = " ".join(text.lower().split())
    if d and d in l and len(d) > 30 and len(l) < 2 * len(d):
        r.error("long_description near-duplicate of description")


def check_manifest(pkg: Path, r: Result) -> dict:
    m = yaml.safe_load((pkg / "manifest.yaml").read_text(encoding="utf-8")) or {}
    for f in MANIFEST_REQUIRED:
        if f not in m:
            r.error(f"manifest missing {f}")
    if not NAME_RE.match(str(m.get("name", ""))):
        r.error("manifest.name not DNS-label format")
    if m.get("market_type") not in ("spot", "contract"):
        r.error("manifest.market_type invalid")
    symbols = m.get("trading_symbols") or []
    norm = {str(s).upper() for s in symbols}
    for s in symbols:
        if "/" in s or ":" in s or " " in s:
            r.error(f"symbol {s} not exchange-native")
    for field in ("display_name", "description"):
        for tok in SYMBOL_TOKEN_RE.findall(str(m.get(field, "")).upper()):
            if tok not in norm:
                r.error(f"manifest.{field} mentions {tok} outside trading_symbols")
    for field in ("display_name_i18n", "description_i18n"):
        block = m.get(field)
        if not isinstance(block, dict):
            r.error(f"manifest.{field} missing")
        else:
            for loc in I18N:
                if not str(block.get(loc, "")).strip():
                    r.error(f"manifest.{field} missing locale {loc}")
    sc = m.get("strategy_config") or {}
    if isinstance(sc.get("trading_symbols"), list) and [s.upper() for s in sc["trading_symbols"]] != [s.upper() for s in symbols]:
        r.error("strategy_config.trading_symbols != trading_symbols")
    if m.get("decision_mode") not in ("deterministic", "llm_assisted", "agentic"):
        r.error("decision_mode invalid")
    if m.get("backtest_support") not in ("full", "none"):
        r.error("backtest_support invalid")
    if m.get("runtime_profile") not in ("deterministic", "llm_bounded", "agentic"):
        r.error("runtime_profile invalid")
    ok = m.get("output_kind", "trade_strategy")
    em = m.get("execution_mode")
    fts = m.get("follow_trade_supported")
    if ok != "selection_basket" and em is None:
        r.error("execution_mode required")
    if em == "follow_trade" and fts is not True:
        r.error("follow_trade requires follow_trade_supported true")
    if ok == "trade_strategy" and em != "follow_trade":
        r.error("trade_strategy requires follow_trade")
    if m.get("runtime_profile") == "llm_bounded" and m.get("backtest_support") == "full":
        r.error("llm_bounded requires backtest_support none")
    if m.get("backtest_support") == "none" and em == "follow_trade" and m.get("runtime_profile") != "llm_bounded":
        r.error("live-only playbooks cannot default to follow_trade")
    if (m.get("backtest_support") == "full" or em == "follow_trade"):
        try:
            if float(str(sc.get("margin_budget", "0"))) <= 0:
                r.error("strategy_config.margin_budget must be positive")
        except ValueError:
            r.error("strategy_config.margin_budget not numeric")
    sched = m.get("schedule")
    if isinstance(sched, dict) and sched.get("cron"):
        tz = sched.get("tz") or sched.get("timezone")
        if not tz:
            r.error("schedule.tz required")
        else:
            try:
                ZoneInfo(str(tz))
            except Exception:
                r.error("schedule.tz not a valid IANA zone")
        parts = str(sched["cron"]).split()
        if len(parts) not in (5, 6):
            r.error("schedule.cron must have 5 or 6 fields")
        else:
            mm = re.fullmatch(r"\*/(\d+)", parts[0])
            if (mm and int(mm.group(1)) < 15) or parts[0] == "*":
                r.error("schedule.cron more frequent than 15 minutes")
    ucs = m.get("user_config_schema") or {}
    for name, spec in ucs.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("type") not in ("string", "integer", "number", "boolean", "array"):
            r.error(f"user_config_schema.{name}.type unsupported")
        if name not in sc:
            r.error(f"user_config_schema.{name} not in strategy_config")
        elif "default" in spec and str(spec["default"]) != str(sc[name]) and spec["default"] != sc[name]:
            r.error(f"user_config_schema.{name}.default != strategy_config.{name}")
    check_long_description(m.get("long_description"), str(m.get("description") or ""), r)
    return m


def check_backtest(pkg: Path, manifest: dict, r: Result, src_text: str) -> None:
    path = pkg / "backtest.yaml"
    if not path.exists():
        return
    if manifest.get("backtest_support") != "full":
        r.error("backtest.yaml only allowed with backtest_support full")
    b = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    venue = b.get("venue") or {}
    for f in ("name", "account_type", "oms_type"):
        if not venue.get(f):
            r.error(f"backtest.venue.{f} missing")
    if not venue.get("starting_balances"):
        r.error("backtest.venue.starting_balances missing")
    strat = b.get("strategy") or {}
    for f in ("module", "class"):
        if not strat.get(f):
            r.error(f"backtest.strategy.{f} missing")
    insts = b.get("instruments") or ([b["instrument"]] if isinstance(b.get("instrument"), dict) else [])
    if not insts:
        r.error("backtest instruments missing")
    syms = set()
    for i, inst in enumerate(insts):
        p = f"backtest.instruments[{i}]"
        if inst.get("kind") not in ("spot", "currency_pair", "perpetual", "perpetual_contract", "perp"):
            r.error(f"{p}.kind invalid")
        for f in ("id", "bar_type", "base_currency", "quote_currency", "price_increment", "size_increment"):
            if not str(inst.get(f, "")).strip():
                r.error(f"{p}.{f} missing")
        for f in ("price_precision", "size_precision"):
            if not isinstance(inst.get(f), int):
                r.error(f"{p}.{f} must be int")
        for f in ("maker_fee", "taker_fee"):
            if f not in inst:
                r.error(f"{p}.{f} missing")
        if inst.get("kind") in ("perpetual", "perpetual_contract", "perp") and not inst.get("settlement_currency"):
            r.error(f"{p}.settlement_currency missing")
        syms.add(str(inst.get("raw_symbol") or inst.get("symbol") or str(inst.get("id", "")).split(".")[0]).upper())
        if "provider" in inst:
            r.error(f"{p} must not declare provider")
    want = {s.upper() for s in (manifest.get("strategy_config", {}).get("trading_symbols") or manifest.get("trading_symbols") or [])}
    if want and syms != want:
        r.error(f"backtest symbols {sorted(syms)} != manifest {sorted(want)}")
    req = (b.get("data_requirements") or {}).get("required_bar_fields")
    if req is not None:
        if not isinstance(req, list) or not req:
            r.error("required_bar_fields must be non-empty list")
        else:
            seen = set()
            for f in req:
                if not re.fullmatch(r"[a-z][a-z0-9_]*", str(f)):
                    r.error(f"required_bar_fields {f} not lower_snake_case")
                if f in seen:
                    r.error(f"required_bar_fields duplicate {f}")
                seen.add(f)
                if str(f) not in src_text:
                    r.error(f"required_bar_fields {f} never referenced in src/**")


def _attr_path(node: ast.AST) -> list[str]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return list(reversed(parts))


def _is_fixed_round(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str" and node.args:
        node = node.args[0]
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "round" and len(node.args) == 2


def _mutable_default(node: ast.AST | None) -> str:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return type(node).__name__.lower()
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "dict", "set"):
        return node.func.id + "()"
    return ""


def check_src(pkg: Path, manifest: dict, r: Result) -> None:
    src = pkg / "src"
    local_roots = {p.stem for p in src.glob("*.py")} | {p.name for p in src.iterdir() if p.is_dir()}
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(pkg).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as e:
            r.error(f"{rel}: syntax error line {e.lineno}: {e.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    root = a.name.split(".")[0]
                    if root in BLOCKED_IMPORTS:
                        r.error(f"{rel}: blocked import {a.name} (line {node.lineno})")
                    elif root not in ALLOWED_IMPORTS and root not in local_roots:
                        r.error(f"{rel}: disallowed import {a.name} (line {node.lineno})")
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                root = (node.module or "").split(".")[0]
                if root in BLOCKED_IMPORTS:
                    r.error(f"{rel}: blocked import from {node.module} (line {node.lineno})")
                elif root not in ALLOWED_IMPORTS and root not in local_roots:
                    r.error(f"{rel}: disallowed import from {node.module} (line {node.lineno})")
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else ""
                if name in ("eval", "exec", "compile", "__import__"):
                    r.error(f"{rel}: {name}() not allowed (line {node.lineno})")
                path_ = _attr_path(node.func)
                if path_ and path_[-1] in ("cancel_all_orders", "close_all_positions") and path_[0] == "self" and not node.args and not node.keywords:
                    r.error(f"{rel}: self.{path_[-1]}() requires instrument_id (line {node.lineno})")
                if path_[-3:] == ["trade", "helpers", "resolve_contract_tpsl"]:
                    if node.args:
                        r.error(f"{rel}: resolve_contract_tpsl is keyword-only (line {node.lineno})")
                    for kw in node.keywords:
                        if kw.arg is None or kw.arg not in TPSL_KW:
                            r.error(f"{rel}: resolve_contract_tpsl unsupported keyword {kw.arg} (line {node.lineno})")
                if path_ and path_[-1] in ("open_long_market", "open_short_market"):
                    for kw in node.keywords:
                        if kw.arg in ("tp_trigger_price", "sl_trigger_price") and _is_fixed_round(kw.value):
                            r.error(f"{rel}: fixed round() on {kw.arg} (line {node.lineno})")
                if path_ and "data" in path_:
                    for kw in node.keywords:
                        if kw.arg == "provider":
                            r.error(f"{rel}: provider= passed to getagent.data call (line {node.lineno})")
            elif isinstance(node, ast.Attribute) and node.attr in ("__builtins__", "__subclasses__", "__import__"):
                r.error(f"{rel}: access to {node.attr} not allowed (line {node.lineno})")
            elif isinstance(node, ast.ClassDef) and any(_attr_path(b)[-1:] == ["StrategyConfig"] for b in node.bases):
                for st in node.body:
                    val = st.value if isinstance(st, (ast.AnnAssign, ast.Assign)) else None
                    desc = _mutable_default(val)
                    if desc:
                        r.error(f"{rel}: StrategyConfig mutable default {desc} (line {st.lineno})")
        if rel in ("src/main.py", "src/main_live.py"):
            _check_live_guards(tree, rel, r)


def _check_live_guards(tree: ast.AST, rel: str, r: Result) -> None:
    def is_guard(test: ast.AST) -> bool:
        for n in ast.walk(test):
            if isinstance(n, ast.Call) and _attr_path(n.func)[-1:] in (["should_follow_trade"], ["is_follow_trade"]):
                return True
            if isinstance(n, ast.Constant) and n.value == "follow_trade":
                return True
        return False

    def visit(node: ast.AST, inside_run: bool, guarded: bool) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inside_run = node.name == "run"
        if inside_run and isinstance(node, ast.If) and is_guard(node.test):
            guarded = True
        if inside_run and isinstance(node, ast.Call):
            path_ = _attr_path(node.func)
            if len(path_) >= 2 and path_[-1] in MUTATIONS and "trade" in path_ and not guarded:
                r.error(f"{rel}: unguarded trade mutation {'.'.join(path_)} in run() (line {node.lineno})")
            if path_[-2:] == ["runtime", "emit_signal_or_follow"]:
                for kw in node.keywords:
                    visit(kw.value, inside_run, True if kw.arg == "execute_trade" else guarded)
                for a in node.args:
                    visit(a, inside_run, guarded)
                return
        for child in ast.iter_child_nodes(node):
            visit(child, inside_run, guarded)

    visit(tree, False, False)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    pkg = Path(sys.argv[1]).resolve()
    r = Result()
    check_structure(pkg, r)
    manifest = check_manifest(pkg, r)
    src_text = "\n".join(p.read_text(encoding="utf-8") for p in (pkg / "src").rglob("*.py"))
    check_backtest(pkg, manifest, r, src_text)
    check_src(pkg, manifest, r)
    for w in r.warnings:
        print(f"WARNING: {w}")
    for e in r.errors:
        print(f"ERROR: {e}")
    print("Validation PASSED" if not r.errors else f"Validation FAILED ({len(r.errors)} errors)")
    return 0 if not r.errors else 1


if __name__ == "__main__":
    sys.exit(main())
