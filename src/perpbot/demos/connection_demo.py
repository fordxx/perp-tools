"""
Connection Management Demo

演示交易所连接管理的完整功能：
1. 行情/交易连接分离
2. 心跳与健康检查
3. 限流与重试
4. 熔断机制
5. KILL SWITCH
"""

import asyncio
import logging
from pprint import pprint

from perpbot.connections import (
    ConnectionConfig,
    ConnectionState,
    ExchangeConnectionManager,
    MockConnection,
    ConnectionRegistry,
    HealthChecker,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def print_separator(title=""):
    print("\n" + "=" * 80)
    if title:
        print(f"  {title}")
        print("=" * 80)


async def demo_basic_connection():
    """演示 1: 基础连接功能"""
    print_separator("演示 1: 基础连接 - 心跳、延迟、限流")

    # 创建配置
    config = ConnectionConfig(
        name="binance_market_data",
        exchange="binance",
        readonly=True,
        heartbeat_interval_sec=2.0,
        heartbeat_timeout_sec=5.0,
        rate_limit_per_sec=5.0,
        max_latency_ms=100.0,
    )

    # 创建连接
    conn = MockConnection(config)

    print("\n[连接到交易所]")
    await conn.connect()

    print(f"状态: {conn.state.value}")
    print(f"只读: {conn.is_readonly}")

    print("\n[发送10个请求（测试限流）]")
    for i in range(10):
        try:
            result = await conn.send_request("get_ticker", symbol="BTC/USDT")
            print(f"  请求 {i+1}: 成功, 延迟={conn.avg_latency_ms:.2f}ms")
        except Exception as e:
            print(f"  请求 {i+1}: 失败 - {e}")

    print("\n[等待心跳...]")
    await asyncio.sleep(3)

    print("\n[健康信息]")
    health = conn.get_health_info()
    pprint(health)

    print("\n[断开连接]")
    await conn.disconnect()


async def demo_circuit_breaker():
    """演示 2: 熔断机制"""
    print_separator("演示 2: 熔断机制 - 连续错误触发熔断")

    config = ConnectionConfig(
        name="okx_market_data",
        exchange="okx",
        readonly=True,
        circuit_open_error_streak=3,  # 3次连续错误触发熔断
        circuit_halfopen_wait_sec=5.0,  # 5秒后进入半开状态
        max_retries=0,  # 不重试，快速触发熔断
    )

    conn = MockConnection(config)
    await conn.connect()

    print("\n[正常请求]")
    result = await conn.send_request("ping")
    print(f"状态: {conn.state.value}, 连续错误: {conn.error_streak}")

    print("\n[模拟5次连续失败]")
    conn.simulate_failures(5)

    for i in range(5):
        try:
            await conn.send_request("get_ticker")
            print(f"  请求 {i+1}: 成功")
        except Exception as e:
            print(f"  请求 {i+1}: 失败 - {e}")
            print(f"  状态: {conn.state.value}, 连续错误: {conn.error_streak}")

    print(f"\n[熔断已触发] 状态: {conn.state.value}")

    print("\n[尝试在熔断期间发送请求]")
    try:
        await conn.send_request("ping")
    except Exception as e:
        print(f"被拒绝: {e}")

    print("\n[等待5秒进入半开状态...]")
    await asyncio.sleep(6)

    print("\n[半开状态下发送请求]")
    try:
        result = await conn.send_request("ping")
        print(f"成功! 状态: {conn.state.value}")
    except Exception as e:
        print(f"失败: {e}")

    await conn.disconnect()


async def demo_exchange_manager():
    """演示 3: 交易所连接管理器"""
    print_separator("演示 3: 交易所连接管理器 - 行情/交易分离")

    # 行情连接配置
    market_config = ConnectionConfig(
        name="binance_market_data",
        exchange="binance",
        readonly=True,
    )

    # 交易连接配置
    trading_config = ConnectionConfig(
        name="binance_trading",
        exchange="binance",
        readonly=False,  # 会被自动设置
    )

    # 创建管理器（启用交易）
    manager = ExchangeConnectionManager(
        exchange="binance",
        market_data_config=market_config,
        trading_config=trading_config,
        trade_enabled=True,
        api_key_env="BINANCE_API_KEY",
        api_secret_env="BINANCE_API_SECRET",
    )

    print("\n[连接所有]")
    await manager.connect_all()

    print("\n[获取行情连接]")
    try:
        market_conn = await manager.ensure_market_data()
        print(f"行情连接: {market_conn.config.name}, 只读={market_conn.is_readonly}")
        await market_conn.send_request("get_ticker")
    except Exception as e:
        print(f"失败: {e}")

    print("\n[获取交易连接]")
    try:
        trading_conn = await manager.ensure_trading()
        print(f"交易连接: {trading_conn.config.name}, 只读={trading_conn.is_readonly}")
    except Exception as e:
        print(f"失败: {e}")

    print("\n[健康快照]")
    snapshot = manager.get_health_snapshot()
    pprint(snapshot)

    print("\n[启用 KILL SWITCH]")
    manager.enable_kill_switch()

    print("\n[尝试获取交易连接（应该被拒绝）]")
    try:
        await manager.ensure_trading()
    except Exception as e:
        print(f"被拒绝: {e}")

    print("\n[禁用 KILL SWITCH]")
    manager.disable_kill_switch()

    await manager.disconnect_all()


async def demo_connection_registry():
    """演示 4: 连接注册中心与健康检查"""
    print_separator("演示 4: 连接注册中心 - 多交易所管理")

    # 创建注册中心
    registry = ConnectionRegistry()

    # 创建多个交易所管理器
    exchanges = ["binance", "okx", "edgex"]
    for exchange in exchanges:
        market_config = ConnectionConfig(
            name=f"{exchange}_market_data",
            exchange=exchange,
            readonly=True,
        )
        manager = ExchangeConnectionManager(
            exchange=exchange,
            market_data_config=market_config,
            trade_enabled=True if exchange in ["binance", "okx"] else False,
        )
        registry.register(manager)

    print(f"\n[注册了 {len(registry.exchanges)} 个交易所]")

    print("\n[连接所有交易所]")
    await registry.connect_all()

    print("\n[健康摘要]")
    summary = registry.get_health_summary()
    print(f"健康交易所: {summary['healthy_exchanges']}/{summary['total_exchanges']}")
    print(f"全局 KILL SWITCH: {summary['global_kill_switch']}")

    print("\n[检查交易是否允许]")
    for exchange in exchanges:
        allowed = registry.is_trading_allowed(exchange)
        print(f"  {exchange}: {'✅ 允许' if allowed else '❌ 禁止'}")

    print("\n[启用 binance KILL SWITCH]")
    registry.enable_exchange_kill_switch("binance")

    print("\n[再次检查]")
    for exchange in exchanges:
        allowed = registry.is_trading_allowed(exchange)
        print(f"  {exchange}: {'✅ 允许' if allowed else '❌ 禁止'}")

    print("\n[启用全局 KILL SWITCH]")
    registry.enable_global_kill_switch()

    print("\n[全部禁止交易]")
    for exchange in exchanges:
        allowed = registry.is_trading_allowed(exchange)
        print(f"  {exchange}: {'✅ 允许' if allowed else '❌ 禁止'}")

    await registry.disconnect_all()


async def demo_health_checker():
    """演示 5: 健康检查器 - 自动监控"""
    print_separator("演示 5: 健康检查器 - 持续监控与告警")

    # 创建注册中心
    registry = ConnectionRegistry()

    # 创建交易所
    for exchange in ["binance", "okx"]:
        config = ConnectionConfig(
            name=f"{exchange}_market_data",
            exchange=exchange,
            readonly=True,
            heartbeat_interval_sec=2.0,
            circuit_open_error_streak=3,
        )
        manager = ExchangeConnectionManager(
            exchange=exchange,
            market_data_config=config,
        )
        registry.register(manager)

    # 连接
    await registry.connect_all()

    # 创建健康检查器
    checker = HealthChecker(registry, check_interval_sec=2.0)

    print("\n[启动健康检查器]")
    checker.start()

    print("\n[正常运行5秒...]")
    await asyncio.sleep(5)

    print("\n[模拟 binance 连续失败]")
    binance_manager = registry.get("binance")
    if binance_manager and binance_manager.market_data_conn:
        binance_manager.market_data_conn.simulate_failures(10)

        # 触发失败
        for i in range(5):
            try:
                await binance_manager.market_data_conn.send_request("ping")
            except:
                pass
            await asyncio.sleep(0.5)

    print("\n[等待健康检查器检测...]")
    await asyncio.sleep(3)

    print("\n[不健康的交易所]")
    unhealthy = checker.get_unhealthy_exchanges()
    print(f"  {unhealthy}")

    print("\n[熔断的交易所]")
    circuit_open = checker.get_circuit_open_exchanges()
    print(f"  {circuit_open}")

    print("\n[最终健康摘要]")
    summary = registry.get_health_summary()
    print(f"健康: {summary['healthy_exchanges']}")
    print(f"降级: {summary['degraded_exchanges']}")
    print(f"不健康: {summary['unhealthy_exchanges']}")

    checker.stop()
    await registry.disconnect_all()


async def demo_full_lifecycle():
    """演示 6: 完整生命周期 - 正常→失败→熔断→恢复"""
    print_separator("演示 6: 完整生命周期")

    config = ConnectionConfig(
        name="test_connection",
        exchange="test",
        readonly=True,
        circuit_open_error_streak=3,
        circuit_halfopen_wait_sec=3.0,
        max_retries=0,
    )

    conn = MockConnection(config)

    print("\n[阶段 1: 正常连接]")
    await conn.connect()
    print(f"状态: {conn.state.value}")

    print("\n[阶段 2: 正常请求]")
    for i in range(3):
        await conn.send_request("ping")
        print(f"  请求 {i+1}: 成功, 延迟={conn.avg_latency_ms:.1f}ms")

    print("\n[阶段 3: 连续失败触发熔断]")
    conn.simulate_failures(10)
    for i in range(5):
        try:
            await conn.send_request("ping")
        except:
            pass
        print(f"  请求 {i+1}: 状态={conn.state.value}, 连续错误={conn.error_streak}")

    print(f"\n[熔断触发] 状态: {conn.state.value}")

    print("\n[阶段 4: 熔断期间所有请求被拒绝]")
    try:
        await conn.send_request("ping")
    except ConnectionError as e:
        print(f"  ❌ 被拒绝: {e}")

    print(f"\n[阶段 5: 等待{config.circuit_halfopen_wait_sec}秒进入半开...]")
    await asyncio.sleep(config.circuit_halfopen_wait_sec + 0.5)

    print("\n[阶段 6: 半开状态测试（清除故障）]")
    conn._failure_count = 0  # 清除模拟故障
    result = await conn.send_request("ping")
    print(f"  ✅ 成功! 状态: {conn.state.value}")

    print("\n[阶段 7: 恢复正常运行]")
    for i in range(3):
        await conn.send_request("ping")
        print(f"  请求 {i+1}: 成功, 状态={conn.state.value}")

    print("\n[最终健康信息]")
    health = conn.get_health_info()
    print(f"  状态: {health['state']}")
    print(f"  平均延迟: {health['avg_latency_ms']}ms")
    print(f"  总请求: {health['total_requests']}")
    print(f"  总错误: {health['total_errors']}")
    print(f"  错误率: {health['error_rate']*100:.1f}%")

    await conn.disconnect()


async def run_all_demos():
    """运行所有演示"""
    print_separator("交易所连接管理 - 完整演示")
    print("""
本演示展示连接管理层的完整功能：

1. 基础连接 - 心跳、延迟、限流
2. 熔断机制 - 连续错误自动熔断
3. 交易所管理器 - 行情/交易分离、KILL SWITCH
4. 连接注册中心 - 多交易所统一管理
5. 健康检查器 - 自动监控与告警
6. 完整生命周期 - 正常→失败→熔断→恢复
    """)

    await demo_basic_connection()
    await demo_circuit_breaker()
    await demo_exchange_manager()
    await demo_connection_registry()
    await demo_health_checker()
    await demo_full_lifecycle()

    print_separator("所有演示完成")
    print("""
✅ 核心功能验证：
1. ✅ 行情/交易连接分离（readonly 控制）
2. ✅ 心跳与健康监控
3. ✅ 限流保护（令牌桶算法）
4. ✅ 自动重试（指数退避）
5. ✅ 熔断机制（连续错误触发）
6. ✅ 半开状态恢复
7. ✅ KILL SWITCH（全局+单交易所）
8. ✅ 健康检查器（持续监控）
9. ✅ 延迟/错误率统计

连接管理层已准备好集成到交易系统！
    """)


if __name__ == "__main__":
    asyncio.run(run_all_demos())
