# playbooks-bitget-agent

GetAgent (Bitget) trading Playbooks authored with the `@bitget-ai/getagent-skill`
package contract. Each Playbook is an uploadable package under `playbooks/`;
specifications, parameter tables and evaluation policy live under `docs/`.

| Playbook | Version | Market | Status |
|---|---|---|---|
| [`runeclaw-intraday-session-flow`](playbooks/runeclaw-intraday-session-flow/) | v0.10.0 | Bitget USDT-M perps passing the liquidity scan (BTC, ETH, SOL, XRP), 15m execution, Signal B only (2.5× volume, 2R target, midpoint entry = v0.5 behaviour; close entry optional), 180 min time stop | v0.1–v0.3.1 FAIL (best PF 0.88, DD ≥ 11 %); v0.4 FAIL (PF 1.03, DD 5.9 %); v0.5 FAIL (PF 1.07, DD 5.7 %); v0.6 **FAIL** (PF 1.02, DD 5.8 %, +0.6 %); v0.5 out-of-sample **FAIL** (PF 0.59, DD 21.5 %); v0.8 **FAIL** (in-sample PF 1.01, DD 10.4 %; out-of-sample PF 0.52, DD 21.2 %); v0.9 cost-filter research: passes in-sample only, not adopted; v0.10 Signal C (opening-range breakout): fails all three windows, not adopted; no live run |

## Layout

```
playbooks/<name>/            uploadable package (README, manifest.yaml, backtest.yaml, src/)
docs/<name>/                 PARAMETERS.md, PSEUDOCODE.md, VERSIONING.md, CHANGELOG.md, PREFLIGHT.md, UNIVERSE.md, OOS_v0.5.md, CONFIRM_v0.8.1.md, RESEARCH_v0.9.md, RESEARCH_v0.10.md, PREMISE_REVIEW.md
tools/check_package.py       mirror of the skill's static validator (+ repo consistency checks)
tools/gen_params_table.py    regenerates PARAMETERS.md from src/params.py, checks manifest defaults
tests/                       unit tests for the pure rule modules (features, risk)
research/                    offline research: public-data fetch, local replay, trade analysis (no API key)
```

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 tools/check_package.py playbooks/runeclaw-intraday-session-flow
python3 tools/gen_params_table.py --check
```

Then run the official validator from the installed skill:
`python3 <skill>/scripts/validate.py ./playbooks/runeclaw-intraday-session-flow/`.

Never commit a Bitget ACCESS-KEY. Keys are supplied in chat at upload time only.
