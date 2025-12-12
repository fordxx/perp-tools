#!/bin/bash
# 📋 四大交易所实盘连接测试 - 快速命令参考

# ============================================================
# 🚀 快速开始
# ============================================================

# 1️⃣ 查看完整准备报告
cat TESTNET_READY_REPORT.md

# 2️⃣ 编辑配置文件
nano .env

# 3️⃣ 运行测试

# === OKX + Hyperliquid 测试 (推荐先测) ===
python test_multi_exchange.py --exchanges okx hyperliquid

# === 所有交易所测试 ===
python test_multi_exchange.py --exchanges all

# === 详细日志输出 ===
python test_multi_exchange.py --exchanges okx --verbose

# ============================================================
# 📦 虚拟环境管理
# ============================================================

# 查看所有虚拟环境
ls -la venv_*

# 创建新虚拟环境
python3 -m venv venv_binance

# 激活虚拟环境
source venv_okx/bin/activate
source venv_hyperliquid/bin/activate
source venv_binance/bin/activate
source venv_bitget/bin/activate

# 安装包
pip install okx python-dotenv
pip install hyperliquid-python-sdk python-dotenv
pip install ccxt python-dotenv  # 用于币安和 BITGET

# 退出虚拟环境
deactivate

# ============================================================
# 🧪 单个交易所测试
# ============================================================

# OKX 测试
python test_okx.py --inst BTC-USDT
python test_okx.py --inst ETH-USDT

# Hyperliquid 测试
python test_hyperliquid.py --symbol BTC/USDC
python test_hyperliquid.py --symbol ETH/USDC

# 币安测试 (需先创建 venv_binance)
python test_binance.py --symbol BTC/USDT

# BITGET 测试 (需先创建 venv_bitget)
python test_bitget.py --inst BTC-USDT

# ============================================================
# 📖 查看文档
# ============================================================

# 完整准备报告
cat TESTNET_READY_REPORT.md

# 详细测试指南
cat TESTNET_CONNECTION_GUIDE.md

# 快速开始指南
cat QUICK_START_TESTNET.md

# ============================================================
# 🔍 故障排查
# ============================================================

# 检查 Python 环境
python3 --version

# 检查虚拟环境中的包
source venv_okx/bin/activate
pip list | grep -E "okx|ccxt|dotenv"
deactivate

# 检查 .env 配置
cat .env | grep -E "^OKX_|^BINANCE|^BITGET|^HYPERLIQUID"

# 运行详细日志
python test_multi_exchange.py --exchanges okx --verbose

# ============================================================
# 📋 配置示例
# ============================================================

cat << 'EOF' > .env.local
# OKX Demo Trading
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_ENV=testnet

# Hyperliquid (可选)
# HYPERLIQUID_ACCOUNT_ADDRESS=0xxxx
# HYPERLIQUID_PRIVATE_KEY=xxxx
# HYPERLIQUID_ENV=testnet

# 币安 Testnet
# BINANCE_API_KEY=your_key
# BINANCE_API_SECRET=your_secret
# BINANCE_ENV=testnet

# BITGET
# BITGET_API_KEY=your_key
# BITGET_API_SECRET=your_secret
# BITGET_PASSPHRASE=your_passphrase
# BITGET_ENV=testnet
EOF

# ============================================================
# 📊 批量测试脚本
# ============================================================

# 一键测试所有交易所
bash << 'EOF'
#!/bin/bash
cd /home/fordxx/perp-tools

echo "🚀 开始四交易所实盘连接测试..."
echo ""

# 测试 OKX
echo "1️⃣ 测试 OKX..."
python test_okx.py --inst BTC-USDT

# 测试 Hyperliquid
echo ""
echo "2️⃣ 测试 Hyperliquid..."
python test_hyperliquid.py --symbol BTC/USDC

# 测试币安 (如果配置了)
echo ""
echo "3️⃣ 测试币安..."
python test_binance.py --symbol BTC/USDT || echo "⏭️ 币安未配置"

# 测试 BITGET (如果配置了)
echo ""
echo "4️⃣ 测试 BITGET..."
python test_bitget.py --inst BTC-USDT || echo "⏭️ BITGET 未配置"

echo ""
echo "✅ 测试完成！"
EOF

# ============================================================
# 🔐 安全检查
# ============================================================

# 确保 .env 不在 Git 中
git check-ignore .env

# 列出敏感文件
echo "⚠️ 敏感文件检查:"
echo "- .env (应该被忽略)"
echo "- 虚拟环境 (应该被忽略)"
ls -la | grep -E "\.env|venv_"

# ============================================================
# 📝 有用的单行命令
# ============================================================

# 快速测试 OKX
source venv_okx/bin/activate && python test_okx.py --inst BTC-USDT && deactivate

# 快速测试 Hyperliquid
source venv_hyperliquid/bin/activate && python test_hyperliquid.py --symbol BTC/USDC && deactivate

# 快速测试所有已配置的交易所
python test_multi_exchange.py --exchanges okx hyperliquid

# 查看所有虚拟环境的 Python 版本
for venv in venv_*/; do echo "=== $venv ==="; $venv/bin/python --version; done

# ============================================================
# 💡 提示
# ============================================================

# 使用 --verbose 标记获得详细日志:
# python test_multi_exchange.py --exchanges okx --verbose

# 使用 --help 查看所有选项:
# python test_multi_exchange.py --help

# 检查虚拟环境中是否安装了所需的包:
# pip list | grep okx
# pip list | grep hyperliquid

# 更新 .env.example 中的配置:
# cp .env.example .env

# ============================================================
