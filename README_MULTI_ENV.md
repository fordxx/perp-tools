# perp-tools Multi-Venv Playbook (V2 Event-Driven)

**版本:** V2  
**最后更新:** 2025-12-12

本文档详细说明如何在 V2 Event-Driven 架构下管理多个 Python 虚拟环境，以支持 8 个交易所的并行集成。

## 项目结构
```
perp-tools/
    venv_extended/
    venv_paradex/
    venv_binance/
    venv_okx/
    venv_bybit/
    venv_edgex/
    venv_backpack/
    venv_grvt/
    venv_aster/
    scripts/
        run_extended.sh
        run_paradex.sh
        run_binance.sh
        run_okx.sh
        run_bybit.sh
        run_edgex.sh
        run_backpack.sh
        run_grvt.sh
        run_aster.sh
    requirements/
        extended.txt
        paradex.txt
        binance.txt
        okx.txt
        bybit.txt
        edgex.txt
        backpack.txt
        grvt.txt
        aster.txt
    README_MULTI_ENV.md
```

## 1. 为什么多 venv 是专业量化方案
- 每个交易所 SDK 带来独立依赖栈（`websockets`、`eth-account`、`httpx`、`grvt-pysdk` 等）会互相冲突，单一解释器无法同时满足；多 venv 允许隔离运行范围，保持核心库版本清晰、部署可控。
- 多环境也提升安全性：可以针对敏感 API Key 只在特定 venv 中加载，减少全局暴露面；同时便于团队成员在同一代码库中并行维护多个交易所测试用例。
- 结合 CI/CD 时，每个小环境只需安装与目标交易所相关依赖，缩短编译与审计时间，配合容器或虚拟化更容易追踪变更。

## 2. 如何创建 venv
1. 确认本地 Python 版本（推荐 `python3.11` 或 `python3.12`）后，从项目根目录执行：
   ```bash
   python -m venv venv_extended
   python -m venv venv_paradex
   python -m venv venv_binance
   python -m venv venv_okx
   python -m venv venv_bybit
   python -m venv venv_edgex
   python -m venv venv_backpack
   python -m venv venv_grvt
   python -m venv venv_aster
   ```
2. 激活环境并确认 `pip` 版本（以 Extended 为例）：
   ```bash
   source venv_extended/bin/activate
   python -m pip install --upgrade pip setuptools wheel
   deactivate
   ```
3. 重复上述步骤为每个 `venv_*` 目录准备基础环境，便于后续安装专属依赖。

## 3. 如何安装 requirements
每个环境对应 `requirements/*.txt`：
- Extended（x10）：`requirements/extended.txt`
- Paradex：`requirements/paradex.txt`
- Binance：`requirements/binance.txt`
- OKX：`requirements/okx.txt`
- Bybit：`requirements/bybit.txt`
- EdgeX：`requirements/edgex.txt`
- Backpack：`requirements/backpack.txt`
- GRVT：`requirements/grvt.txt`
- Aster：`requirements/aster.txt`

示例：
```bash
source venv_extended/bin/activate
pip install -r requirements/extended.txt
deactivate
```
请按照上述流程分别激活每个环境并安装对应依赖；若 CI 报告失败，可以通过 `pip check` 查找版本解算冲突。

## 4. 如何运行每个交易所
项目提供 `scripts/run_<exchange>.sh` 快捷脚本，会自动：
1. 定位项目根目录
2. 激活对应虚拟环境
3. 执行交易所测试脚本（支持参数透传）

使用示例：
```bash
./scripts/run_extended.sh --symbol ETH/USD --limit-offset 0.04
./scripts/run_paradex.sh --symbol BTC/USDT
./scripts/run_binance.sh --symbol BTCUSDT --depth 10
./scripts/run_okx.sh --inst BTC-USDT
./scripts/run_bybit.sh --symbol BTCUSDT
./scripts/run_edgex.sh --symbol BTC/USDT
./scripts/run_backpack.sh --symbol ETH/USDT
./scripts/run_grvt.sh --symbol BTC/USDT
./scripts/run_aster.sh --symbol BTC/USDT
```
上述脚本分别针对 `test_extended.py`、`test_paradex.py`、`test_binance.py`、`test_okx.py`、`test_bybit.py`、`test_edgex.py`、`test_backpack.py`、`test_grvt.py` 与 `test_aster.py`，可配合 `--help` 获取更多参数。

## 5. 如何在 VS Code 切换解释器
1. 打开命令面板 `Ctrl+Shift+P` → `Python: Select Interpreter`
2. 选择 `<项目路径>/venv_<exchange>/bin/python`（推荐为每个交易所创建 `.vscode/settings.json`，例如：
   ```json
   {
     "python.pythonPath": "${workspaceFolder}/venv_paradex/bin/python"
   }
   ```
3. 可再配合 `.vscode/launch.json` 为调试样板指定 `envFile` 与入口脚本，避免误用全局解释器。

## 6. 如何在服务器上部署
### Systemd 示例（以 Extended 为例）
```
[Unit]
Description=Extended smoke test
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/home/trader/perp-tools
ExecStart=/home/trader/perp-tools/scripts/run_extended.sh --symbol ETH/USD
User=trader
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```
保存为 `/etc/systemd/system/perp-extended.service`，之后执行 `sudo systemctl daemon-reload && sudo systemctl enable --now perp-extended.service`。

### Cron 示例（每天 08:15 轮询 Paradex）
```
15 8 * * * cd /home/trader/perp-tools && ./scripts/run_paradex.sh --symbol BTC/USDT >> /var/log/perp/paradex.log 2>&1
```
定义 `LOG_DIR` 并为每个交易所建 separate log 以便追踪各自的运行状态。

## 7. 不同交易所依赖冲突的根本原因
- `websockets`：Extended/x10 依赖 `websockets 13.x`，Paradex 要求 `>=15.x`，其余交易所也频繁升级，如果共用解释器会引发协程协议与 `subprotocol` 不兼容；独立环境可锁定适配版本。
- `eth-account` 与 `PyNaCl`：Extended 需要 `eth-account>=0.13` 的签名优化，同一时间 Paradex 和 GRVT 仍然依赖 `<0.12` 甚至 `PyNaCl` 做 ED25519，而 Backpack 额外依赖 `PyNaCl` 签名库；版本混用会导致参数校验不一致与运行时导入错误。
- `httpx`, `requests`, `grvt-pysdk`, `fast-stark-crypto` 等网络/加密库在 `charset-normalizer`、`urllib3`、`cffi` 等底层依赖上常发生冲突；多 venv 让团队分别升级、回滚或与自己的测试脚本同步依赖状态。

## 8. 推荐的目录规范
- `venv_<exchange>/`：虚拟环境目录，仅存 Python 解释器和 site-packages，避免加入版本控制。
- `scripts/`：启动脚本统一命名 `run_<exchange>.sh`，shell 内自动定位根目录。
- `requirements/<exchange>.txt`：依赖分离，保持每条依赖强制表明版本的理由。
- `test_<exchange>.py`：每个环境对应一个独立的 smoke test，便于快速验证 SDK 兼容性。
- `README_MULTI_ENV.md`：多环境手册，及时更新依赖变动与运行方式。
- `configs/`（可选）：若公开多个 `env` 配置，可按交易所维持单独 `.env` 文件并在脚本中加载，避免混用 sensitive 信息。
- 针对 EdgeX/Backpack/GRVT/Aster，也请在主 README 或 docs 中同步列出对应的 `venv_*` 与 `requirements/*.txt`，让新同事一眼掌握全局依赖概览。

## 9. 注意事项（Python 3.12 兼容性）
- `websockets>=10` 内部已支持 `SSL` 扩展并在 3.12 上测试通过，但请使用 `pip install --upgrade pip setuptools wheel` 以避免编译失败。
- `pybit` 与 `python-binance` 目前在 3.12 上没有已知关键问题，但仍建议在本地测试 `pip check`，并定期锁定 `pipenv lock` 或 `poetry lock` 以便追踪 `manylinux` 轮换。
- `httpx>=0.24`、`grvt-pysdk`、`fast-stark-crypto` 与 `PyNaCl` 等库在 3.12 上主要靠 wheel 支持；如遇编译或导入失败，可借助 `pip install --upgrade pip setuptools wheel` 或短暂回退至 `python3.11`，再锁定成功版本。
- activation scripts（`source venv_* /bin/activate`）需确保 `bash` 版本与 `PYTHONPATH` 清晰，避免与系统级 `python3` 混淆。

## 额外提示
- 若要支持更多交易所（如 dYdX、Coinbase 等），请复制 `requirements/<name>.txt`、对应 `venv_<name>` 与 `scripts/run_<name>.sh`，并保持 README 中的第 7 点中说明的冲突记录。
- 可以借助 `test_all_exchanges.py` 作为通用入口，配合 `--trading` 标志快速验证 `perpbot.exchanges.*` 模块。
