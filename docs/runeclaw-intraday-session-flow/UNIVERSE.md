# Universe scan — Bitget USDT-M perpetuals (2026-11-09 17:10 UTC)

Source: `GET /api/v2/mix/market/contracts` + `GET /api/v2/mix/market/tickers` (productType=USDT-FUTURES). 884 contracts listed, all `symbolStatus: normal`; 420 are RWA stock-token perpetuals.

Playbook liquidity rule: 24h quote volume ≥ 200M USDT **and** spread ≤ 3 bps at signal time. The table lists every contract above 100M so the margin is visible. `Pass` = both rules at scan time.

| Symbol | RWA | 24h volume (M USDT) | Spread (bps) | Tick | Lot | Pass | In default universe |
|---|---|---|---|---|---|---|---|
| BTCUSDT | no | 3,705 | 0.01 | 1e-1 | 1e-4 | yes | yes |
| ETHUSDT | no | 2,385 | 0.05 | 1e-2 | 1e-2 | yes | yes |
| SOXLUSDT | yes | 664 | 1.79 | 1e-2 | 1e-2 | yes | opt-in |
| SOLUSDT | no | 261 | 0.12 | 1e-3 | 1e-1 | yes | yes |
| SNDKUSDT | yes | 256 | 1.11 | 1e-2 | 1e-3 | yes | opt-in |
| XRPUSDT | no | 253 | 0.91 | 1e-4 | 1 | yes | yes |
| KORUUSDT | yes | 218 | 1.31 | 1e-3 | 1e-2 | yes | opt-in |
| ZECUSDT | no | 176 | 0.08 | 1e-2 | 1e-3 | no | no |
| XAUUSDT | yes | 133 | 0.02 | 1e-2 | 1e-2 | no | no |
| SOXSUSDT | yes | 125 | 2.50 | 1e-3 | 1e-2 | no | no |
| JCTUSDT | no | 124 | 5.66 | 1e-6 | 1 | no | no |
| CLUSDT | yes | 103 | 0.69 | 1e-3 | 1e-2 | no | no |
| MUUSDT | yes | 101 | 0.27 | 1e-2 | 1e-2 | no | no |

## Decisions

* **Default universe (v0.2)**: the four crypto contracts that pass: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT. SOLUSDT and XRPUSDT sit just above the 200M line, so the live volume gate will drop them on quiet days; that is intended.
* **Opt-in**: SOXLUSDT, SNDKUSDT, KORUUSDT pass today but are RWA stock-token perpetuals whose price action follows US equity hours. They are selectable by subscribers but excluded from the default universe and from the official backtest until a version tests them separately.
* **Everything else** fails the volume rule by a wide margin today. The live path re-checks volume and spread on every run, so the universe shrinks automatically when liquidity leaves; widening it requires a new version with a fresh scan.
* Re-run the scan (PREFLIGHT.md step 1) before each new version; this file is the record for v0.2.
