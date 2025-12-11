# Lighter 交易功能测试计划

## 目标与范围

| 功能 | 目标 | 脚本 / 步骤 | 状态 |
|------|------|-------------|------|
| 连接与凭证校验 | 使用 SDK/REST 成功建立连接，确认交易开关 | `python test_lighter.py --skip-trading` | 待执行 |
| 行情查询 | 获取 `ETH/USDT` 等主力交易对的 Bid/Ask 与订单簿 | `test_lighter.py` 自动执行 | 待执行 |
| 账户余额/持仓 | 读取权益、可用余额、持仓方向与数量 | `test_lighter.py` 自动执行 | 待执行 |
| 活跃订单查询 | 枚举未成交订单并校验字段 | `test_lighter.py` 自动执行 | 待执行 |
| 限价单 + 撤单 | 在远离市价的位置挂单，确认可创建并撤销 | `test_lighter.py`（交互式确认） | 待执行 |
| 市价单 + 平仓 | 小额实盘开仓后立即平仓，验证资金与仓位变动 | `test_lighter.py`（交互式确认） | 待执行 |
| WebSocket 推送 | 订阅 `orders`/`positions` 频道，验证推送（后续补完） | `ws_manager` 统一入口 | TODO |
| 本地止盈止损 | 参考 Paradex 测试脚本，待与策略模块统一 | `test_paradex_ws_tp_sl.py` (迁移中) | TODO |

> 状态列会在实测完成后更新，可直接在该文件追加测试日期、订单 ID、资金占用等信息。

---

## 环境准备

1. `pip install lighter-v1-python python-dotenv`
2. `.env` 中至少包含：
   ```env
   LIGHTER_API_KEY=xxxxx
   LIGHTER_PRIVATE_KEY=0xabc...
   LIGHTER_ENV=testnet   # 主网请改为 mainnet
   ```
3. 如果 Lighter 提供专用的 JSON-RPC / API 域名，请额外设置：
   ```env
   LIGHTER_RPC_URL=https://rpc-your-network
   LIGHTER_API_BASE_URL=https://api-your-network
   ```
   这能避免默认的 `mainnet.zklighter.elliot.ai` 返回 404，并支持官方 SDK 正常查询链 ID。
4. 若要在命令行覆盖环境，可使用 `python test_lighter.py --env testnet ...`。
5. 账户余额建议 ≥ 20 USDC，方便完成 0.002 ETH 级别的最小仓位测试。

---

## 执行顺序

1. **只读冒烟**（无交易）：
   ```bash
   python test_lighter.py --skip-trading --symbol ETH/USDT
   ```
   记录连接、行情、余额、持仓、活跃订单的日志输出。

2. **限价单撤单回路**：
   ```bash
   python test_lighter.py --symbol ETH/USDT --size 0.002 --limit-offset 0.04
   ```
   - 根据提示输入 `yes` 继续操作
   - 脚本会在市价 4% 之外挂单，等待 2 秒后提示撤单
   - 记录订单 ID、提交/撤单时间戳、费用（如有）

3. **市价开仓 + 平仓**：
   ```bash
   python test_lighter.py --symbol ETH/USDT --size 0.002 --side buy
   ```
   - 市价买入/卖出均可，脚本将提示是否立即平仓
   - 平仓后记录成交均价、手续费、PNL（可在 Lighter 界面查看）

4. **WebSocket & 止盈止损**（选做）：
   - 通过 `src/perpbot/connections/ws_manager.py` 注册 lighter 配置，观察订单/持仓推送
   - 将 `test_paradex_ws_tp_sl.py` 的监控逻辑迁移为通用模块后，针对 Lighter 实盘验证

---

## 观测要点

- 连接阶段需看到 `✅ Lighter 已连接` 日志，同时 `trading=True`
- 行情接口返回的 bid/ask 不得为 0；订单簿至少 5 档
- 余额查询应显示 USDC，可对比 Lighter UI 是否一致
- 限价单挂出后在 Lighter 页面可见，并能被脚本撤单
- 市价单执行后，`get_account_positions()` 应新增/减少对应仓位
- 撤单/平仓均需记录订单 ID、时间、脚本日志，供 `PARADEX_TEST_SUMMARY.md` 类似的总结引用

---

## 记录模板（执行后填写）

| 日期 | 功能 | 测试结论 | 备注 |
|------|------|----------|------|
| 2025-??-?? | 限价单 + 撤单 | ✅ / ❌ | 订单 ID、价格、数量 |
| 2025-??-?? | 市价开仓 + 平仓 | ✅ / ❌ | 成交价、PNL |
| 2025-??-?? | WebSocket 推送 | ✅ / ❌ | push 样例 |

> 建议将最终总结写入 `PARADEX_TEST_SUMMARY.md` 同级的新文档 `LIGHTER_TEST_SUMMARY.md`，保持测试成果可追溯。
