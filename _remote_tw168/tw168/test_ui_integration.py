#!/usr/bin/env python3
"""
TW168 UI服务器集成测试脚本
用于验证UI服务器是否正常运行并测试各个API端点
"""

import requests
import json
import sys
import time
from pathlib import Path

# UI服务器配置
UI_URL = "http://localhost:9000"
TIMEOUT = 5

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.RESET}")

def test_health_check():
    """测试健康检查端点"""
    print_header("1. 健康检查")
    try:
        response = requests.get(f"{UI_URL}/health", timeout=TIMEOUT)
        if response.status_code == 200:
            print_success("健康检查通过")
            print(f"   响应: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print_error(f"健康检查失败: 状态码 {response.status_code}")
            return False
    except Exception as e:
        print_error(f"无法连接到UI服务器: {e}")
        return False

def test_main_page():
    """测试主页是否可访问"""
    print_header("2. 主页访问")
    try:
        response = requests.get(f"{UI_URL}/", timeout=TIMEOUT)
        if response.status_code == 200:
            if "TW168" in response.text and "交易控制面板" in response.text:
                print_success("主页加载成功")
                print(f"   页面大小: {len(response.text)} 字节")
                return True
            else:
                print_error("主页内容不正确")
                return False
        else:
            print_error(f"主页加载失败: 状态码 {response.status_code}")
            return False
    except Exception as e:
        print_error(f"无法访问主页: {e}")
        return False

def test_system_status():
    """测试系统状态API"""
    print_header("3. 系统状态API")
    try:
        response = requests.get(f"{UI_URL}/api/system/status", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            print_success("系统状态API可用")
            print(f"   交易所: {data.get('exchange', 'N/A')}")
            print(f"   交易模式: {'实盘' if data.get('trading_enabled') else '纸上交易'}")
            print(f"   运行时间: {data.get('uptime', 0)}秒")
            print(f"   信号总数: {data.get('total_signals', 0)}")
            print(f"   活跃仓位: {data.get('active_positions', 0)}")
            return True
        else:
            print_error(f"系统状态API失败: 状态码 {response.status_code}")
            return False
    except Exception as e:
        print_error(f"无法获取系统状态: {e}")
        return False

def test_signal_history():
    """测试信号历史API"""
    print_header("4. 信号历史API")
    try:
        response = requests.get(f"{UI_URL}/api/signals/history?limit=10", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            history = data.get('history', [])
            print_success("信号历史API可用")
            print(f"   历史记录数: {len(history)}")
            if history:
                print(f"   最新信号: {history[-1]['timestamp']}")
                print(f"   交易对: {history[-1]['signal']['instId']}")
            return True
        else:
            print_error(f"信号历史API失败: 状态码 {response.status_code}")
            return False
    except Exception as e:
        print_error(f"无法获取信号历史: {e}")
        return False

def test_send_signal():
    """测试信号发送API（会失败因为没有真实密钥）"""
    print_header("5. 信号发送API（测试失败情况）")
    
    test_payload = {
        "instId": "ETH-USDT-SWAP",
        "tf": "1h",
        "side": "long",
        "admin_key": "test-invalid-key"
    }
    
    try:
        response = requests.post(
            f"{UI_URL}/signals/send",
            json=test_payload,
            timeout=TIMEOUT
        )
        
        if response.status_code == 403:
            print_success("API正确拒绝了无效的密钥")
            print(f"   预期结果: 403 Forbidden")
            return True
        elif response.status_code == 500:
            print_warning("API返回服务器错误（可能主应用未运行）")
            print(f"   状态码: {response.status_code}")
            return False
        else:
            print_error(f"API返回意外状态码: {response.status_code}")
            print(f"   响应: {response.text[:200]}")
            return False
            
    except Exception as e:
        print_error(f"无法测试信号发送: {e}")
        return False

def test_css_assets():
    """测试静态资源是否可访问"""
    print_header("6. 静态资源检查")
    
    resources = [
        ("/static/style.css", "CSS样式文件"),
    ]
    
    all_ok = True
    for url, name in resources:
        try:
            response = requests.get(f"{UI_URL}{url}", timeout=TIMEOUT)
            if response.status_code == 200:
                print_success(f"{name}: 可访问 ({len(response.text)} 字节)")
            else:
                print_warning(f"{name}: 状态码 {response.status_code}")
                all_ok = False
        except Exception as e:
            print_error(f"{name}: {e}")
            all_ok = False
    
    return all_ok

def test_page_load_time():
    """测试页面加载时间"""
    print_header("7. 性能测试")
    
    try:
        start_time = time.time()
        response = requests.get(f"{UI_URL}/", timeout=TIMEOUT)
        load_time = (time.time() - start_time) * 1000  # 转换为毫秒
        
        if response.status_code == 200:
            print_success(f"页面加载时间: {load_time:.2f}ms")
            if load_time < 1000:
                print_success("✓ 性能良好")
                return True
            elif load_time < 3000:
                print_warning("⚠ 性能一般")
                return True
            else:
                print_warning("⚠ 性能较慢，请检查网络")
                return True
        return False
    except Exception as e:
        print_error(f"性能测试失败: {e}")
        return False

def main():
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║         TW168 UI服务器测试套件                            ║")
    print("║         Testing Suite for TW168 UI Server                  ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")
    
    print_info(f"UI服务器地址: {UI_URL}")
    print_info(f"测试超时: {TIMEOUT}秒")
    
    # 等待一秒后开始测试
    time.sleep(1)
    
    # 运行所有测试
    tests = [
        ("健康检查", test_health_check),
        ("主页访问", test_main_page),
        ("系统状态", test_system_status),
        ("信号历史", test_signal_history),
        ("信号发送", test_send_signal),
        ("静态资源", test_css_assets),
        ("性能测试", test_page_load_time),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print_error(f"测试异常: {e}")
            results.append((test_name, False))
    
    # 打印总结
    print_header("📊 测试总结")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status} - {test_name}")
    
    print(f"\n{Colors.BOLD}总体结果: {passed}/{total} 通过{Colors.RESET}")
    
    if passed == total:
        print_success("所有测试都通过了！UI服务器运行正常。✨")
        return 0
    elif passed >= total * 0.7:
        print_warning(f"部分测试失败，但UI基本可用")
        return 1
    else:
        print_error("大部分测试失败，请检查UI服务器配置")
        return 2

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_warning("\n\n测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print_error(f"测试失败: {e}")
        sys.exit(1)
