# Pre-flight checklist before the first upload / run

Run from the repository root. Nothing below needs the Bitget API key except
the upload/run/publish calls in step 6.

## 1. Confirm the three symbols on Bitget USDT-FUTURES and copy tick/lot sizes

```bash
for s in BTCUSDT ETHUSDT SOLUSDT; do
  curl -s "https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES&symbol=$s" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin)["data"][0]; print({k:d[k] for k in ("symbol","symbolStatus","pricePlace","priceEndStep","volumePlace","minTradeNum","makerFeeRate","takerFeeRate","fundInterval")})'
done
```

Expect `symbolStatus == "normal"`. Update `backtest.yaml` if `pricePlace`,
`priceEndStep`, `volumePlace`, `minTradeNum` or the fee rates differ from the
values written there (BTC 0.1 / 0.001, ETH 0.01 / 0.01, SOL 0.001 / 0.1,
maker 0.02 % / taker 0.06 %). This lookup could not be executed from the
authoring environment (outbound access to api.bitget.com was blocked), so the
values in `backtest.yaml` are the commonly published ones and must be verified.

## 2. Probe replay data coverage (sandbox run does this automatically)

`main_backtest.run` pages `crypto.futures.kline(..., exchange="bitget",
interval="15m")` and refuses any symbol with < 70 % bar coverage. Check
`meta.data` in the emitted signal for `coverage`, `first`, `last` per symbol.

## 3. Local static validation (official Bitget skill validator)

```bash
npx @bitget-ai/getagent-skill install          # once; installs skills/getagent/
python3 <skill-dir>/scripts/validate.py ./playbooks/runeclaw-intraday-session-flow/
```

Expect `Validation PASSED`. The repository mirror `tools/check_package.py`
re-implements the same rules and must also pass:

```bash
python3 tools/check_package.py playbooks/runeclaw-intraday-session-flow
python3 -m unittest discover -s tests -v
```

## 4. Package

```bash
cd playbooks/runeclaw-intraday-session-flow && tar czf ../../runeclaw-intraday-session-flow.tar.gz . && cd -
```

## 5. Key handling

* Never paste the ACCESS-KEY into any file in this repository.
* Provide it to the agent only in chat, immediately before upload, and rotate it
  in Bitget after the session if it was ever shown on screen or in a screenshot.

## 6. Upload → run → read → confirm → publish

```bash
curl -X POST -H "ACCESS-KEY: <access_key>" -F "package=@runeclaw-intraday-session-flow.tar.gz" \
     "https://api.bitget.com/api/v1/playbook/upload"          # returns draft_id
# POST /api/v1/playbook/run with the draft_id  (historical evaluation)
# read evaluation.json verdict: PENDING / PASS / FAIL  — only PASS may go live
# POST /api/v1/playbook/confirm, then publish, only after an explicit decision
```

Starting or stopping a live subscription is done by the account owner in the
GetAgent page, never by the agent.
