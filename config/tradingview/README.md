# tv168 配置（可选）

TradingView Webhook 集成默认只靠环境变量即可运行；如果你想把多交易所映射/别名/每所下单 size 维护成文件，可使用 YAML。

## 使用

- 在 `.env` 设置 `PERPBOT_TV_CONFIG_PATH=config/tradingview/example.yaml`
- 或启动时导出 `PERPBOT_TV_CONFIG_PATH=/abs/path/to/tv168.yaml`

## 字段

- `enabled`: true/false
- `secret`: webhook secret（建议仍用 env 覆盖）
- `default_exchange`: payload 未带 `exchange` 时使用
- `exchange_allowlist`: 允许的交易所列表（可空）
- `exchange_aliases`: 把用户输入的 exchange 别名映射到系统 exchange name
- `symbol_allowlist`: 允许的 symbol/instId（支持 `ETH-USDT-SWAP` / `ETH/USDT` / `SOLUSDT.P` 等）
- `symbol_aliases`: 把 TV 的 instId（如 `SOLUSDT.P`）映射成更明确的合约标识（如 `SOL/USDT` 或 `SOL-USDT-SWAP`）
- `order_size`: 默认下单 size
- `order_size_by_exchange`: 每个交易所覆盖默认 size
- `symbol_overrides_by_exchange`: 每个交易所覆盖 canonical symbol（`BASE/QUOTE`）到该交易所实际下单 symbol（可选）
