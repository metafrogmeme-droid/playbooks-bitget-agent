# playbooks-bitget-agent

GetAgent (Bitget) trading Playbooks authored with the `@bitget-ai/getagent-skill`
package contract. Each Playbook is an uploadable package under `playbooks/`;
specifications, parameter tables and evaluation policy live under `docs/`.

| Playbook | Version | Market | Status |
|---|---|---|---|
| [`runeclaw-intraday-session-flow`](playbooks/runeclaw-intraday-session-flow/) | v0.3.1 | Bitget USDT-M perps passing the liquidity scan (BTC, ETH, SOL, XRP), 15m execution | v0.1 FAIL (PF 0.88, DD 11.4 %), v0.2 FAIL (PF 0.78, DD 14.0 %), v0.3.0 FAIL (PF 0.84, DD 11.4 %); v0.3.1 **PENDING** |

## Layout

```
playbooks/<name>/            uploadable package (README, manifest.yaml, backtest.yaml, src/)
docs/<name>/                 PARAMETERS.md, PSEUDOCODE.md, VERSIONING.md, CHANGELOG.md, PREFLIGHT.md, UNIVERSE.md
tools/check_package.py       mirror of the skill's static validator (+ repo consistency checks)
tools/gen_params_table.py    regenerates PARAMETERS.md from src/params.py, checks manifest defaults
tests/                       unit tests for the pure rule modules (features, risk)
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
