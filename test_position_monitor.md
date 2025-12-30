# 持仓监控服务测试指南

## 功能说明

持仓监控服务会自动监控所有 OKX 持仓，并根据盈亏比自动分批平仓：

**止盈梯度：**
- 1.5R → 平仓 70%
- 2R   → 平仓 15%
- 2.5R → 平仓 10%
- 3R   → 平仓全部（剩余 5%）

**回撤保护：**
- 到达 2R 后，回撤至 0.75R → 全部平仓

其中 R (Risk-Reward Ratio) 盈亏比计算：
```
做多：RR = (当前价 - 开仓价) / (开仓价 - 止损价)
做空：RR = (开仓价 - 当前价) / (止损价 - 开仓价)
```

## 使用流程

### 1. 启动监控服务

```bash
chmod +x start_position_monitor.sh
./start_position_monitor.sh
```

服务会后台运行，每 5 秒检查一次所有持仓。

### 2. 开仓测试

有持仓后，监控服务会自动跟踪。可以通过以下方式创建测试持仓：

#### 方式 A：使用 TV Webhook 开仓
```bash
# 启动 tv168 服务（如果还没启动）
bash /tmp/restart_tv168.sh

# 发送 TV 信号开仓
bash test_tv_webhook_sol.sh
```

#### 方式 B：直接下单
```bash
PYTHONPATH=src .venv/bin/python test_okx_sol_order_auto.py
```

### 3. 监控日志

```bash
# 实时查看监控日志
tail -f /tmp/position_monitor.log

# 查看最近的监控记录
tail -50 /tmp/position_monitor.log | grep "📊\|🎯\|✅"
```

### 4. 模拟价格变化测试

由于实际价格变化缓慢，无法快速测试分批平仓逻辑。建议：

1. **小仓位实盘测试**：使用 0.01 SOL 开仓，等待实际价格变化
2. **修改止损价测试**：人为调整止损价，使当前价格达到不同的 R 值

例如，如果当前：
- 开仓价：124 USDT
- 当前价：125 USDT
- 盈利：1 USDT

想要触发 1.5R (平仓70%)，需要：
- 止损价设置为：124 - 1/1.5 = 123.33 USDT

### 5. 查看持仓状态

```bash
# 查询当前持仓
PYTHONPATH=src .venv/bin/python check_okx_order.py

# 查看 OKX 网页端
# https://www.okx.com/trade-swap/sol-usdt-swap
```

### 6. 停止监控服务

```bash
pkill -f "perpbot.position_monitor"
```

## 配置参数

在 `.env` 中配置：

```bash
# 监控间隔（秒）
POSITION_MONITOR_INTERVAL=5.0

# OKX 配置（必需）
OKX_API_KEY=你的Key
OKX_API_SECRET=你的Secret
OKX_PASSPHRASE=你的Passphrase
OKX_ENV=prod
```

## 日志说明

### 正常运行日志
```
📊 SOL/USDT: price=125.00 rr=1.2 max_rr=1.2 size=0.1000
```
- `price`: 当前价格
- `rr`: 当前盈亏比
- `max_rr`: 历史最高盈亏比
- `size`: 当前持仓数量

### 触发平仓日志
```
🎯 触发平仓: symbol=SOL/USDT rr=1.52 close_pct=70.0% reason=1.5R_平仓70%
🔄 分批平仓: symbol=SOL/USDT side=long size=0.0700 (70.0%) reason=1.5R_平仓70%
✅ 平仓成功: order_id=3139366944687087616 symbol=SOL/USDT size=0.0700 price=125.50
```

### 错误日志
```
❌ 平仓失败: order_id=error-... symbol=SOL/USDT
```

## 注意事项

1. **止损价获取**：
   - 当前版本在发现新持仓时，使用简单估算（入场价 ±2%）作为止损价
   - 最好在开仓时同时下止损单，监控服务会读取真实止损价（TODO）

2. **最小下单量**：
   - OKX SOL 最小 0.01，如果分批平仓数量 < 0.01 会跳过

3. **双向持仓**：
   - 需要 OKX 账户开启双向持仓模式
   - 监控服务支持同时监控多空持仓

4. **回撤保护**：
   - 只有达到过 2R 后才启用
   - 触发条件：回撤至 0.75R

## 测试场景示例

### 场景 1：正常分批止盈

1. 开仓：0.1 SOL @ 124 USDT，止损 122 USDT
2. 价格上涨到 127 USDT → RR = 1.5 → 平仓 70% (0.07 SOL)
3. 价格继续上涨到 128 USDT → RR = 2.0 → 平仓 15% (0.015 SOL)
4. 价格继续上涨到 129 USDT → RR = 2.5 → 平仓 10% (0.01 SOL)
5. 价格继续上涨到 130 USDT → RR = 3.0 → 平仓剩余 5% (0.005 SOL → 小于最小单位，跳过)

### 场景 2：回撤保护

1. 开仓：0.1 SOL @ 124 USDT，止损 122 USDT
2. 价格上涨到 128 USDT → RR = 2.0 → 平仓 15%，剩余 0.085 SOL
3. 价格回撤到 125.5 USDT → RR = 0.75 → 触发回撤保护 → 全部平仓 0.085 SOL

## 远程部署

上传到远程服务器：

```bash
# 上传监控服务代码
scp src/perpbot/position_monitor.py user@remote:/path/to/perp-tools/src/perpbot/
scp src/perpbot/exchanges/okx.py user@remote:/path/to/perp-tools/src/perpbot/exchanges/
scp start_position_monitor.sh user@remote:/path/to/perp-tools/

# SSH 到远程
ssh user@remote
cd /path/to/perp-tools

# 启动监控
./start_position_monitor.sh
```

## 进阶：整合到系统服务

可以使用 systemd 让监控服务开机自启：

```bash
# 创建 systemd 服务文件
sudo vi /etc/systemd/system/position-monitor.service
```

内容：
```ini
[Unit]
Description=Position Monitor Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/perp-tools
Environment="PYTHONPATH=src"
ExecStart=/path/to/perp-tools/.venv/bin/python -m perpbot.position_monitor
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable position-monitor
sudo systemctl start position-monitor
sudo systemctl status position-monitor
```

查看日志：
```bash
sudo journalctl -u position-monitor -f
```
