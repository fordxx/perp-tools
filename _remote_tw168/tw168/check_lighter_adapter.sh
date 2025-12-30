#!/bin/bash
# Lighter 异步适配器 - 集成验证清单

set -e

echo "============================================================"
echo "Lighter 异步适配器 - 集成验证"
echo "============================================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_file() {
    local file=$1
    local desc=$2
    
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅${NC} $desc: $file"
        return 0
    else
        echo -e "${RED}❌${NC} $desc: $file (未找到)"
        return 1
    fi
}

check_string() {
    local file=$1
    local pattern=$2
    local desc=$3
    
    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo -e "${GREEN}✅${NC} $desc"
        return 0
    else
        echo -e "${RED}❌${NC} $desc"
        return 1
    fi
}

# 1. 检查文件是否存在
echo "1️⃣  检查文件结构..."
check_file "app/lighter_adapter.py" "适配器文件"
check_file "test_lighter_adapter.py" "测试脚本"
check_file "LIGHTER_ASYNC_ADAPTER.md" "详细文档"
check_file "LIGHTER_ASYNC_QUICK_REF.md" "快速参考"
check_file "LIGHTER_ASYNC_IMPLEMENTATION.md" "实施总结"
echo ""

# 2. 检查 main.py 集成
echo "2️⃣  检查 main.py 集成..."
check_string "app/main.py" "from app.lighter_adapter import create_lighter_adapter" "导入适配器"
check_string "app/main.py" "exchange = create_lighter_adapter" "使用适配器工厂"
check_string "app/main.py" "await exchange.connect()" "异步连接调用"
echo ""

# 3. 检查适配器内容
echo "3️⃣  检查适配器实现..."
check_string "app/lighter_adapter.py" "class LighterAsyncAdapter" "适配器类定义"
check_string "app/lighter_adapter.py" "async def connect" "异步连接方法"
check_string "app/lighter_adapter.py" "async def place_order" "异步下单方法"
check_string "app/lighter_adapter.py" "async def cancel_all_orders" "异步撤单方法"
check_string "app/lighter_adapter.py" "asyncio.to_thread" "线程桥接"
echo ""

# 4. 检查测试脚本
echo "4️⃣  检查测试脚本..."
check_string "test_lighter_adapter.py" "async def test_adapter" "测试函数"
check_string "test_lighter_adapter.py" "asyncio.run" "异步运行"
echo ""

# 5. 语法检查
echo "5️⃣  Python 语法检查..."
if command -v python3 &> /dev/null; then
    if python3 -m py_compile app/lighter_adapter.py 2>/dev/null; then
        echo -e "${GREEN}✅${NC} app/lighter_adapter.py 语法正确"
    else
        echo -e "${RED}❌${NC} app/lighter_adapter.py 语法错误"
    fi
    
    if python3 -m py_compile test_lighter_adapter.py 2>/dev/null; then
        echo -e "${GREEN}✅${NC} test_lighter_adapter.py 语法正确"
    else
        echo -e "${RED}❌${NC} test_lighter_adapter.py 语法错误"
    fi
else
    echo -e "${YELLOW}⚠️${NC}  Python3 未安装，跳过语法检查"
fi
echo ""

# 6. 检查依赖
echo "6️⃣  检查依赖项..."
check_string "app/lighter_adapter.py" "import asyncio" "asyncio 导入"
check_string "app/lighter_adapter.py" "import logging" "logging 导入"
echo ""

# 7. 代码统计
echo "7️⃣  代码统计..."
echo "适配器代码行数: $(wc -l < app/lighter_adapter.py)"
echo "测试代码行数: $(wc -l < test_lighter_adapter.py)"
echo "文档总行数: $(cat LIGHTER_ASYNC_*.md 2>/dev/null | wc -l)"
echo ""

# 8. 快速测试建议
echo "============================================================"
echo "下一步操作建议"
echo "============================================================"
echo ""
echo "1. 运行单元测试:"
echo "   python test_lighter_adapter.py"
echo ""
echo "2. 启动服务测试:"
echo "   uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "3. 查看日志:"
echo "   tail -f tw168.log | grep -E '(Lighter|adapter)'"
echo ""
echo "4. 完整测试流程:"
echo "   bash scripts/test_lighter.sh"
echo ""
echo "5. 阅读文档:"
echo "   cat LIGHTER_ASYNC_QUICK_REF.md"
echo ""

# 总结
echo "============================================================"
echo "验证完成"
echo "============================================================"
