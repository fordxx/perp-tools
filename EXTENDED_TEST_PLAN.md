# Extended 交易测试计划 (V2 Event-Driven)

**版本:** V2  
**最后更新:** 2025-12-12  
**架构:** EventBus 驱动的异步执行

## 覆盖范围

| 功能 | 说明 | 脚本 / 命令 | 状态 |
|------|------|-------------|------|
| 连接与认证 | 使用 `ExtendedClient` 的 API Key + Stark 私钥初始化 | `python test_extended.py --skip-trading` | 待执行 |
| 行情 + 订单簿 | 验证 `info/markets/{symbol}/stats` + `/info/markets/{symbol}/orderbook` 接口（建议使用 `ETH-USD`, `BTC-USD`） | 同上 | 待执行 |
| 账户余额 / 持仓 / 活跃订单 | 读取 `/user/balance`, `/user/positions`, `/user/orders` | 同上 | 待执行 |
| 限价下单 + 撤单 | 在偏离市价位置下单后撤单，记录订单 ID | `python test_extended.py --symbol ETH/USD --limit-offset 0.04` | 待执行 |
| 市价开仓 + 平仓 | 小额市价成交并立即平仓，验证仓位更新 | `python test_extended.py --symbol ETH/USD --size 0.002` | 待执行 |

---

## 环境准备

1. 安装依赖：`pip install x10_perpetual lighter-v1-python python-dotenv`
2. `.env` 中至少设置（`EXTENDED_VAULT_NUMBER` 必填，它表示 Extended 控制台中的 Vault/Collateral ID）：
   ```env
   EXTENDED_API_KEY=xxx
   EXTENDED_STARK_PRIVATE_KEY=0x...
   EXTENDED_VAULT_NUMBER=123456
   EXTENDED_ENV=testnet     # 或 mainnet
   ```
   Vault ID 可以在 Extended UI → 资金页 → Vault 详情中找到；Stark 私钥需与 Vault 所在的账户匹配。
3. `LIGHTER_*` 的配置可以保持原样（按需），本计划只关注 Extended。
4. 账户余额建议 ≥ 20 USDC / 对应资产，便于 0.002 ETH 级别深度。

## 参考文档及定位思路

- Extended HTTP API 文档： https://api.docs.extended.exchange/#extended-api-documentation
- `Create or edit order`（`/user/order`）章节描述了必须包含的 Stark 签名、fee、expiry、vault、orderbook 等字段，由 `create_order_object` 负责生成。
- `Get markets` 与 `Get orderbook` 定义了 `/info/markets/{symbol}/stats` 与 `/info/markets/{symbol}/orderbook` 的返回结构；推荐优先验证 `ETH-USD`、`BTC-USD`。

在执行 `test_extended.py` 的交易回路时，如果接口报 400/失败，脚本会在 `❌ 下单失败` 后打印 `详细信息`，输出即是 Extended 返回的 error payload，对于 payload 中的 `error-dc91960b`、`error-xxxx` 可以在上述文档找到对应说明。

---

## 实施步骤

1. 执行查询冒烟：
   ```bash
   python test_extended.py --skip-trading --symbol ETH/USD
   ```
   记录连接、价格、订单簿、余额、持仓、活跃订单的日志。

2. 限价挂单/撤单回路：
   ```bash
   python test_extended.py --symbol ETH/USD --size 0.002 --limit-offset 0.04
   ```
   - 必须输入 `yes` 确认下单/撤单，订单默认偏离 4%，避免立刻成交。
   - 拆解日志：订单 ID、提交/撤销时间、价格。

3. 市价开仓 + 平仓：
   ```bash
   python test_extended.py --symbol ETH/USD --size 0.002 --side buy
   ```
   - 先确认市价买入，脚本会提示是否立即平仓；确认后验证持仓减少。
   - 记录成交价、手续费、任何 PnL 观察。

4. （可选）WebSocket & 止盈策略：通过 `src/perpbot/connections/ws_manager.py` 注册 Extended 频道，对 `orders`/`positions` 做推送验证；`test_paradex_ws_tp_sl.py` 的逻辑可迁移后加入 Extended。

---

## 观测要点

- 连接日志需显示 `✅ Extended connected` 且 `trading=True`。
- 行情接口出的 bid/ask 不能均为 0，订单簿需返回至少 5 档。
- 余额及持仓数据须与 Extended UI 对应。
- 限价单成功撤销后在后台看不到残留订单。
- 市价单开仓产生持仓，平仓后仓位消失。
- 每次交易记录订单 ID、方向、数量、价格与手续费，便于写入 `PARADEX_TEST_SUMMARY.md` 类 summary。
- 出现 `❌ 下单失败` 且后续输出 `详细信息` 时，请对照上面的 API 文档确认：是否缺少 Vault、签名/fee/expiry 等字段或参数值错误。

---

## 记录模板（实测后用）

| 日期 | 功能 | 结论 | 备注 |
|------|------|------|------|
| 2025-??-?? | 连接 + 行情 | ✅ | API Key / Stark 私钥 |
| 2025-??-?? | 限价单 + 撤单 | ✅ | 订单 ID / 价格 |
| 2025-??-?? | 市价开仓 + 平仓 | ✅ | 成交价 / PnL |
