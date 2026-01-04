# TW168 UI 快速开始指南

## 🚀 快速启动

### 方式1：使用启动脚本（推荐）

```bash
# 启动UI服务器
./start_ui_server.sh

# 停止UI服务器
./stop_ui_server.sh
```

### 方式2：手动启动

```bash
# 进入项目目录
cd /home/fordxx/perp-tools/_remote_tw168/tw168

# 启动UI服务器
./.venv/bin/python ui_server.py
```

### 方式3：后台运行

```bash
# 后台启动
nohup ./.venv/bin/python ui_server.py > ui.log 2>&1 &

# 查看日志
tail -f ui.log
```

## 📱 访问UI

启动后，在浏览器中打开：

- **本地**: `http://localhost:9000`
- **远程**: `http://<server-ip>:9000`

如果需要把本地 UI 的信号转发到远程服务器开单，请在本地 `.env` 设置 `TRADING_SERVICE_BASE_URL=http://<remote-ip>:8000`（详见 `UI_USAGE.md`）。

## 🎯 使用流程

### 1. 发送交易信号

```
选择交易对 → 选择时间周期 → 选择方向 → 输入密钥 → 点击发送
```

### 2. 监控交易

- 观看**系统状态**卡片
- 查看**信号历史**面板
- 检查**活跃仓位**数量

### 3. 检查日志

```bash
# 查看UI服务器日志
tail -f ui.log

# 查看主应用日志
tail -f tw168.log
```

## 📊 关键指标

| 指标 | 说明 |
|------|------|
| 系统状态 | 显示应用是否正常运行 |
| 最后信号 | 上一个信号的发送时间 |
| 信号计数 | 已发送的总信号数 |
| 活跃仓位 | 当前开放的仓位数量 |

## 🔐 安全提示

1. **不要分享密钥**
2. **使用强密码**
3. **定期更换密钥** (修改 .env 中的 TV_WEBHOOK_SECRET)
4. **在生产环境使用HTTPS** (配置Nginx反向代理)

## 🐛 故障排除

### 问题：无法访问UI
```bash
# 检查端口是否在监听
netstat -tlnp | grep 9000

# 如果占用，杀死进程
pkill -f "ui_server.py"
```

### 问题：模块错误
```bash
# 重新安装依赖
./.venv/bin/pip install -r requirements.txt
./.venv/bin/pip install jinja2 python-multipart
```

### 问题：权限被拒绝
```bash
# 给脚本添加执行权限
chmod +x start_ui_server.sh stop_ui_server.sh
```

## 📚 更多信息

详见 `UI_USAGE.md` 了解完整的API文档和高级配置。

## 🔗 相关文件

- `ui_server.py` - UI服务器主文件
- `templates/index.html` - 网页界面模板
- `static/style.css` - 样式文件
- `UI_USAGE.md` - 详细使用文档
- `start_ui_server.sh` - 启动脚本
- `stop_ui_server.sh` - 停止脚本

## 💡 常用命令

```bash
# 启动UI
./start_ui_server.sh

# 在另一个终端停止UI
./stop_ui_server.sh

# 查看UI日志
tail -f ui.log

# 查看主应用日志  
tail -f tw168.log

# 后台启动并记录日志
nohup ./.venv/bin/python ui_server.py >> ui.log 2>&1 &

# 查看运行的Python进程
ps aux | grep python

# 测试API端点
curl http://localhost:9000/api/system/status
curl http://localhost:9000/api/signals/history
```

## 📞 需要帮助？

如遇问题，请：
1. 查看日志文件 (ui.log, tw168.log)
2. 检查 UI_USAGE.md 的"常见问题"部分
3. 确保主应用 (app.main) 也在运行
4. 验证所有依赖都已安装

祝您使用愉快！🎉
