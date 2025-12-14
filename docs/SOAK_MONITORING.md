# 📈 Soak 监控与告警（Exchange 连接稳定性）

这套“监控”不是 Prometheus/Grafana，而是把交易所连接/行情查询跑成**可观测、可复现、可自动总结**的长跑体系：`soak` + `dual-runner` + `summary` +（可选）`webhook` 告警。

---

## 1) 单交易所 Soak（推荐）

Soak 会 `connect()` 一次，然后按间隔循环做：
- `get_current_price`
- `get_orderbook`
- （可选）每 N 轮做一次 `get_account_balances / get_account_positions`

每轮都会输出一条结构化日志：`[soak] i=... ok=... fail_rate=... err=...`

### 示例

```bash
# 30 分钟长跑（失败率阈值 0 = 任意失败都退出）
./run_exchange_test.sh paradex --soak 1800 --interval 30 --jitter 0.5 --max-fail-rate 0 --symbol BTC/USDT
```

### 只测行情（跳过账户）

适合 reference-only、或账户权限/凭证还没修好的时候，先暴露“连接/行情”问题：

```bash
./run_exchange_test.sh bitget --auto-test --skip-account --symbol BTC/USDT
./run_exchange_test.sh bitget --soak 1800 --skip-account --account-every 0 --symbol BTC/USDT
```

---

## 2) 双交易所并跑（Dual Runner）

入口脚本：`START_DUAL_EXCHANGE_TEST.sh`

特点：
- A/B 两个交易所各自一条进程并跑
- `RUN_DURATION_SEC` 到点自动停止并生成 summary：`logs/dual_exchange_summary_*.txt`
- `ENABLE_GUARDIAN=true` 时，进程异常退出会自动拉起（并记录重启）

### 常用环境变量

```bash
AUTO_CONFIRM=true \
USE_SOAK=true ENABLE_GUARDIAN=true \
RUN_DURATION_SEC=3600 MONITOR_INTERVAL=30 \
EXCHANGE_A=paradex EXCHANGE_B=extended \
SYMBOL_A=BTC/USDT SYMBOL_B=BTC/USD \
./START_DUAL_EXCHANGE_TEST.sh
```

### market-only（跳过账户）

```bash
AUTO_CONFIRM=true USE_SOAK=true ENABLE_GUARDIAN=true \
SKIP_ACCOUNT_CHECKS=true \
RUN_DURATION_SEC=3600 MONITOR_INTERVAL=30 \
EXCHANGE_A=binance EXCHANGE_B=bitget \
./START_DUAL_EXCHANGE_TEST.sh
```

---

## 3) JSONL 指标（便于聚合/回溯）

`test_exchanges.py` 支持把事件写入 JSONL：
- `--jsonl-log logs/xxx.jsonl`
- 或环境变量 `PERPBOT_JSONL_LOG=logs/xxx.jsonl`

Dual runner 会自动为每个交易所生成同名 JSONL：
- `logs/<exchange>_YYYYmmdd_HHMMSS.jsonl`

---

## 4) Webhook 告警（失败即推送）

设置：
- `--alert-webhook <url>`
- 或环境变量 `PERPBOT_ALERT_WEBHOOK_URL=<url>`
- Dual runner 也支持 `ALERT_WEBHOOK_URL=<url>`

触发：
- `soak_tick` 失败（`ok=false`）/ `soak_abort` 会 POST 一条 JSON 到 webhook。

---

## 5) Soak Profile（按组顺序跑）

Profile 定义在：`config/soak_profiles/*.yaml`

运行：
```bash
python3 scripts/run_soak_profile.py --profile cex_core --duration-sec 3600 --interval-sec 60 --auto-confirm
```

---

## 6) Extended WS 自动降级（重要）

Extended 订单簿 WS 如果持续 `1006/clean close` 等异常，会自动进入 cooldown：暂时不用 WS，强制走 REST snapshot（避免 hammering）。

环境变量：
- `EXTENDED_ORDERBOOK_WS_FAIL_THRESHOLD`：连续失败阈值（默认 8）
- `EXTENDED_ORDERBOOK_WS_DISABLE_COOLDOWN_SEC`：禁用时长（默认 300s）
- `EXTENDED_ORDERBOOK_WS_STALE_DISABLE_SEC`：缓存持续过旧则触发禁用（默认 0 关闭）
- `EXTENDED_DISABLE_ORDERBOOK_WS=1`：手动强制禁用 WS

