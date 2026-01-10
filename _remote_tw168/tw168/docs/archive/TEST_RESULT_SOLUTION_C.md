# 方案 C 测试结果报告

## 测试时间
2025-12-30 20:15 (UTC+8)

## 测试目标
验证 Ladder 挂单自动清理功能的完整流程

## 测试环境

- **服务器**: 3-38-98-169.nip.io:443（旧直连 3.38.98.169:8000 已不推荐）
- **Exchange**: Lighter (mainnet)
- **容器**: tw168-tv-okx-1
- **测试品种**: EIGEN-USDT-SWAP

## 测试步骤

### 1. ZONE 信号 ✅
**请求**:
```json
{
  "type": "ZONE",
  "instId": "EIGEN-USDT-SWAP",
  "tf": "5m",
  "zone": "oversold",
  "close": "0.374"
}
```

**响应**:
```json
{
  "ok": true,
  "type": "ZONE",
  "zone": "OVERSOLD"
}
```

**状态**: ✅ 成功

---

### 2. DIV 信号开仓 ⚠️
**请求**:
```json
{
  "type": "DIV",
  "instId": "EIGEN-USDT-SWAP",
  "tf": "5m",
  "side": "buy"
}
```

**遇到问题**:
```
AttributeError: 'LighterClient' object has no attribute 'get_position'
```

**原因分析**:
- LighterClient 在 `/src/perpbot/exchanges/lighter.py` 中确实有 `get_position` 方法
- 但 Docker 容器中的 `/src` 目录可能没有包含最新代码
- 需要重新构建镜像并确保 `/src` 正确复制

---

## 发现的问题

### 问题 1: Docker 镜像中 /src 目录未更新

**Dockerfile** ([tw168/Dockerfile](Dockerfile)):
```dockerfile
COPY ../../src /src
```

这个路径在 Docker build 上下文中可能无法正确解析。

**解决方案**:
需要确保 `/src` 目录被正确复制到容器中。有两个选择：

**方案 A**: 修改 Dockerfile
```dockerfile
# 在 docker-compose.yml 的 build context 中包含上级目录
# 或使用卷挂载
volumes:
  - ../../src:/src:ro
```

**方案 B**: 切换到 OKX 模式测试
- OKX 的代码已经在容器中且完整
- 可以验证挂单清理逻辑

---

## 代码验证

### ✅ 已验证部分

1. **State 模块**
   ```python
   ✅ pending_orders_by_key 属性存在
   ✅ add_pending_order() 方法正常
   ✅ get_pending_orders() 方法正常
   ✅ clear_pending_orders() 方法正常
   ```

2. **清理函数**
   ```python
   ✅ _cancel_pending_ladder_orders() 函数存在
   ✅ 函数签名正确
   ```

3. **集成点**
   - ✅ Ladder 下单时记录 (main.py:2179-2187)
   - ✅ SL 触发平仓前撤单 (main.py:2538-2539)
   - ✅ 紧急平仓前撤单 (main.py:2673-2674)
   - ✅ Ladder 完成后清理 (main.py:2383-2384)
   - ✅ 无成交撤单后清理 (main.py:2405-2406)

### ⚠️ 待验证部分

由于运行时错误，以下功能尚未实际测试：

- ⏳ Ladder 订单创建
- ⏳ 挂单记录到 state
- ⏳ 平仓时撤单调用
- ⏳ Lighter 平台挂单清理验证

---

## 建议

### 短期解决方案（推荐）

使用 OKX 模式进行测试：

1. **修改环境变量**
   ```bash
   ssh ubuntu@3.38.98.169
   cd /home/ubuntu/tw168
   # 编辑 .env，设置 EXCHANGE=okx
   docker compose restart tv-okx
   ```

2. **重新测试完整流程**
   - ZONE 信号
   - DIV 信号开仓（创建 Ladder）
   - DIV 信号平仓（清理挂单）
   - 验证 OKX 平台无残留挂单

### 长期解决方案

修复 Lighter 部署：

1. **方式 1: 使用卷挂载**
   ```yaml
   # docker-compose.yml
   services:
     tv-okx:
       volumes:
         - ../../src:/src:ro
   ```

2. **方式 2: 修改 Dockerfile build context**
   ```yaml
   # docker-compose.yml
   services:
     tv-okx:
       build:
         context: ../..  # 上级目录
         dockerfile: tw168/Dockerfile
   ```

---

## 结论

### 代码实现 ✅
- 方案 C 的所有代码已正确实现
- State 管理功能正常
- 清理逻辑已集成到所有关键位置

### 部署状态 ⚠️
- 代码已上传到服务器
- Docker 镜像已重新构建
- **但** `/src` 目录可能未正确更新

### 功能验证 ⏳
- 基础功能已验证（state 方法）
- 完整流程因运行时错误未能完成
- 需要修复部署问题或切换到 OKX 模式

---

## 下一步行动

**立即可行**:
1. 切换到 OKX 模式
2. 执行完整测试流程
3. 验证挂单清理功能

**后续优化**:
1. 修复 Lighter 部署问题
2. 在 Lighter 模式下重新测试
3. 两个交易所都验证通过

---

## 附录：日志片段

### 成功的 ZONE 信号
```
INFO: tv_webhook received type=ZONE instId=EIGEN-USDT-SWAP tf=5m zone=oversold
INFO: tv_webhook decision instId=EIGEN-USDT-SWAP tf=5m action=ok
```

### 失败的 DIV 信号
```
INFO: tv_webhook received type=DIV instId=EIGEN-USDT-SWAP tf=5m zone=None
INFO: tv_webhook risk_based_sizing tf=5m risk_usdt=5.0 r_value=0.0025 coins=2019.7613
AttributeError: 'LighterClient' object has no attribute 'get_position'
```

### 期望的成功日志（未出现）
```
INFO: state added_pending_order key=EIGEN-USDT-SWAP:5m order_id=xxx level=L1
INFO: state added_pending_order key=EIGEN-USDT-SWAP:5m order_id=xxx level=L2
INFO: cancel_pending_orders key=EIGEN-USDT-SWAP:5m count=2
INFO: canceled_pending_order key=EIGEN-USDT-SWAP:5m order_id=xxx
INFO: state cleared_pending_orders key=EIGEN-USDT-SWAP:5m count=2
```

---

测试时间: 2025-12-30 20:15
状态: 部分完成 - 需要修复部署或切换到 OKX 模式
