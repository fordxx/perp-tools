# Telegram 通知配置指南

tw168系统使用Telegram发送交易通知和告警。按照以下步骤配置Telegram通知功能。

## 📱 第一步：创建Telegram Bot

1. 在Telegram中搜索并打开 **@BotFather**
2. 发送命令 `/newbot`
3. 按照提示设置bot名称和用户名
4. 创建成功后，BotFather会给你一个 **Token**，类似：
   ```
   1234567890:ABCdefGHIjklMNOpqrsTUVwxyz1234567890
   ```
5. **保存这个Token**，稍后需要用到

## 🆔 第二步：获取Chat ID

### 方法1：使用 @userinfobot

1. 在Telegram中搜索 **@userinfobot**
2. 启动对话，bot会显示你的用户信息
3. 记录显示的 **Id** 数字（例如：`123456789`）

### 方法2：使用API获取

1. 先向你的bot发送任意消息（例如：`/start`）
2. 在浏览器中访问：
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   将 `<YOUR_BOT_TOKEN>` 替换为你的bot token
3. 在返回的JSON中查找 `"chat":{"id":123456789}` 中的id

### 使用群组通知

如果想让bot发送消息到群组：

1. 将bot添加到群组
2. 发送一条消息到群组
3. 访问上述getUpdates链接
4. 查找 `"chat":{"id":-1001234567890}` (群组ID通常是负数)

## ⚙️ 第三步：配置环境变量

### 远程服务器配置

SSH登录到服务器后，编辑 `.env` 文件：

```bash
cd /home/ubuntu/tw168
nano .env
```

在文件末尾添加以下配置：

```bash
# Telegram notifications
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz1234567890
TELEGRAM_CHAT_ID=123456789
```

保存文件（Ctrl+X, Y, Enter）

### 重启服务

```bash
cd /home/ubuntu/tw168
sudo docker compose restart
```

## ✅ 第四步：测试通知

重启服务后，系统会在以下情况发送Telegram通知：

### 错误通知 (notify_error)
- ❌ 止损单下单失败
- ❌ 紧急平仓执行
- ❌ 止损失败率超过阈值（5%）
- ❌ TP单下单失败

### 信息通知 (notify_info)
- ✅ 成功开仓（带止损保护）
- ✅ TP单设置成功

### 通知格式

所有通知会带有 `[tv168]` 前缀，例如：

```
[tv168] ERROR Stop-loss order failed for ETH-USDT-SWAP, executing emergency close
[tv168] INFO ✅ Entry filled: ETH-USDT-SWAP LONG @ $2000.00, SL @ $1950.00
[tv168] ERROR ⚠️ HIGH SL FAILURE RATE: 8.3% (5/60 attempts)
```

## 🧪 手动测试

你可以手动测试Telegram通知是否配置正确：

```bash
# SSH到服务器
ssh -i /home/fordxx/lightsail.pem ubuntu@3.38.98.169

# 进入容器
sudo docker exec -it tw168-tv-okx-1 python3 -c "
from app.notify import notify_info
notify_info('测试消息：Telegram通知配置成功！')
"
```

如果配置正确，你应该会在Telegram收到消息：
```
[tv168] INFO 测试消息：Telegram通知配置成功！
```

## 🔍 故障排查

### 没有收到通知

1. **检查环境变量**
   ```bash
   sudo docker exec tw168-tv-okx-1 env | grep TELEGRAM
   ```
   应该显示你配置的TOKEN和CHAT_ID

2. **检查Bot Token是否正确**
   ```bash
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
   ```
   应该返回bot信息，而不是错误

3. **检查Chat ID是否正确**
   - 确认你已经向bot发送过至少一条消息（例如 `/start`）
   - 群组ID应该是负数（例如 `-1001234567890`）

4. **检查容器日志**
   ```bash
   sudo docker logs tw168-tv-okx-1 --tail 50
   ```
   查看是否有Telegram相关的错误

### Bot无法发送消息到群组

如果bot在群组中，确保：
- Bot有发送消息的权限
- 群组设置中允许bot发送消息
- 使用正确的负数群组ID

## 📋 配置示例

完整的 `.env` 配置示例（仅显示Telegram相关）：

```bash
# ... 其他配置 ...

# Telegram notifications
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz1234567890
TELEGRAM_CHAT_ID=123456789

# 或使用群组
# TELEGRAM_CHAT_ID=-1001234567890
```

## 🔐 安全建议

1. **不要分享Bot Token** - 这相当于bot的密码
2. **定期轮换Token** - 如果怀疑泄露，在@BotFather中重新生成
3. **保护.env文件** - 确保文件权限正确（600）：
   ```bash
   chmod 600 /home/ubuntu/tw168/.env
   ```

## 📚 相关文档

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [BotFather Commands](https://core.telegram.org/bots#6-botfather)
- [Getting Updates](https://core.telegram.org/bots/api#getupdates)

---

配置完成后，你将收到所有重要的交易事件通知，帮助你实时监控系统运行状态！
