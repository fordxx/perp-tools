#!/usr/bin/env python3
"""
持仓监控服务 - 分批止盈和回撤保护

策略：
- 1.5R → 平仓 70%
- 2R   → 平仓 15%
- 2.5R → 平仓 10%
- 3R   → 平仓全部（剩余 5%）
- 回撤保护：到达2R后，回撤至0.75R → 全部平仓
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    """持仓状态追踪"""
    symbol: str
    side: str  # long or short
    size: float  # 当前持仓数量
    entry_price: float  # 开仓均价
    stop_loss: float  # 止损价

    # 状态追踪
    max_rr_reached: float = 0.0  # 达到过的最高盈亏比
    closed_70pct: bool = False  # 是否已平仓70%
    closed_15pct: bool = False  # 是否已平仓15%
    closed_10pct: bool = False  # 是否已平仓10%
    closed_100pct: bool = False  # 是否已全部平仓

    initial_size: float = 0.0  # 初始持仓数量（用于计算分批比例）

    def __post_init__(self):
        if self.initial_size == 0:
            self.initial_size = self.size


class PositionMonitor:
    """持仓监控器"""

    def __init__(self, exchange_client: Any, check_interval: float = 5.0):
        """
        Args:
            exchange_client: OKX 客户端
            check_interval: 检查间隔（秒）
        """
        self.exchange = exchange_client
        self.check_interval = check_interval
        self.position_states: dict[str, PositionState] = {}  # symbol -> state
        self.running = False

    def calculate_rr(self, position: PositionState, current_price: float) -> float:
        """计算当前盈亏比（Risk-Reward Ratio）

        RR = (当前利润) / (风险)
           = (current_price - entry_price) / (entry_price - stop_loss)

        做多：current > entry 为正，current < entry 为负
        做空：current < entry 为正，current > entry 为负
        """
        risk = abs(position.entry_price - position.stop_loss)
        if risk == 0:
            return 0.0

        if position.side == "long":
            profit = current_price - position.entry_price
        else:  # short
            profit = position.entry_price - current_price

        return profit / risk

    def should_close_partial(self, position: PositionState, current_rr: float) -> tuple[bool, float, str]:
        """判断是否应该分批平仓

        Returns:
            (should_close, close_percentage, reason)
        """
        # 3R: 平仓剩余全部（5%）
        if current_rr >= 3.0 and not position.closed_100pct:
            return (True, 1.0, "3R_全部平仓")

        # 2.5R: 平仓10%
        if current_rr >= 2.5 and not position.closed_10pct:
            return (True, 0.10, "2.5R_平仓10%")

        # 2R: 平仓15%
        if current_rr >= 2.0 and not position.closed_15pct:
            return (True, 0.15, "2R_平仓15%")

        # 1.5R: 平仓70%
        if current_rr >= 1.5 and not position.closed_70pct:
            return (True, 0.70, "1.5R_平仓70%")

        # 回撤保护：到达过2R，现在回撤到0.75R
        if position.max_rr_reached >= 2.0 and current_rr <= 0.75:
            return (True, 1.0, "回撤保护_全部平仓")

        return (False, 0.0, "")

    def close_partial_position(
        self,
        position: PositionState,
        close_percentage: float,
        reason: str
    ) -> bool:
        """分批平仓

        Args:
            position: 持仓状态
            close_percentage: 平仓比例（0-1）
            reason: 平仓原因

        Returns:
            成功返回 True
        """
        close_size = position.size * close_percentage

        # 最小下单量检查（OKX SOL 最小 0.01）
        if close_size < 0.01:
            logger.warning(
                f"Close size too small: {close_size} SOL, skipping. "
                f"symbol={position.symbol} reason={reason}"
            )
            return False

        # 确定平仓方向
        close_side = "sell" if position.side == "long" else "buy"

        logger.info(
            f"🔄 分批平仓: symbol={position.symbol} side={position.side} "
            f"size={close_size:.4f} ({close_percentage*100:.1f}%) reason={reason}"
        )

        try:
            # 获取当前价格（用于日志）
            price_quote = self.exchange.get_current_price(position.symbol)
            current_price = (price_quote.ask + price_quote.bid) / 2

            # 调用新的分批平仓方法
            close_order = self.exchange.place_close_order_partial(
                symbol=position.symbol,
                side=close_side,
                size=close_size,
                hedge_mode=True
            )

            if close_order and not close_order.id.startswith("error"):
                logger.info(
                    f"✅ 平仓成功: order_id={close_order.id} symbol={position.symbol} "
                    f"size={close_size:.4f} price={current_price:.2f}"
                )

                # 更新持仓状态
                position.size -= close_size

                # 标记已平仓
                if close_percentage >= 1.0:
                    position.closed_100pct = True
                elif close_percentage >= 0.70:
                    position.closed_70pct = True
                elif close_percentage >= 0.15:
                    position.closed_15pct = True
                elif close_percentage >= 0.10:
                    position.closed_10pct = True

                return True
            else:
                logger.error(
                    f"❌ 平仓失败: order_id={close_order.id if close_order else 'None'} "
                    f"symbol={position.symbol}"
                )
                return False

        except Exception as e:
            logger.exception(f"❌ 平仓异常: symbol={position.symbol} error={e}")
            return False

    def update_positions(self):
        """更新持仓列表"""
        try:
            # 查询 OKX 持仓
            positions = self.exchange.exchange.fetch_positions()

            # 过滤出有持仓的
            active_positions = [
                p for p in positions
                if p.get('contracts', 0) != 0 or p.get('contractSize', 0) != 0
            ]

            # 更新状态
            current_symbols = set()
            for pos in active_positions:
                symbol_raw = pos.get('symbol', '')
                # 转换 SOL/USDT:USDT -> SOL/USDT
                if ':' in symbol_raw:
                    symbol = symbol_raw.split(':')[0]
                else:
                    symbol = symbol_raw

                size = float(pos.get('contracts', pos.get('contractSize', 0)))
                entry_price = float(pos.get('entryPrice', 0))
                side = pos.get('side', 'long')  # long or short

                current_symbols.add(symbol)

                # 如果是新持仓，创建状态
                if symbol not in self.position_states:
                    # 需要从某处获取止损价，暂时使用简单估算（入场价下方2%）
                    stop_loss = entry_price * 0.98 if side == "long" else entry_price * 1.02

                    self.position_states[symbol] = PositionState(
                        symbol=symbol,
                        side=side,
                        size=size,
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        initial_size=size
                    )
                    logger.info(
                        f"📊 发现新持仓: symbol={symbol} side={side} size={size} "
                        f"entry={entry_price:.2f} sl={stop_loss:.2f}"
                    )
                else:
                    # 更新现有持仓大小
                    self.position_states[symbol].size = size

            # 移除已平仓的
            closed_symbols = set(self.position_states.keys()) - current_symbols
            for symbol in closed_symbols:
                logger.info(f"✅ 持仓已关闭: symbol={symbol}")
                del self.position_states[symbol]

        except Exception as e:
            logger.exception(f"❌ 更新持仓失败: {e}")

    def check_and_execute(self):
        """检查所有持仓并执行策略"""
        self.update_positions()

        for symbol, position in list(self.position_states.items()):
            try:
                # 获取当前价格
                price_quote = self.exchange.get_current_price(position.symbol)
                current_price = (price_quote.ask + price_quote.bid) / 2

                # 计算当前盈亏比
                current_rr = self.calculate_rr(position, current_price)

                # 更新最高盈亏比
                if current_rr > position.max_rr_reached:
                    position.max_rr_reached = current_rr

                logger.debug(
                    f"📊 {symbol}: price={current_price:.2f} rr={current_rr:.2f} "
                    f"max_rr={position.max_rr_reached:.2f} size={position.size:.4f}"
                )

                # 判断是否需要平仓
                should_close, close_pct, reason = self.should_close_partial(position, current_rr)

                if should_close:
                    logger.info(
                        f"🎯 触发平仓: symbol={symbol} rr={current_rr:.2f} "
                        f"close_pct={close_pct*100:.1f}% reason={reason}"
                    )
                    self.close_partial_position(position, close_pct, reason)

            except Exception as e:
                logger.exception(f"❌ 处理持仓失败: symbol={symbol} error={e}")

    def run(self):
        """启动监控循环"""
        self.running = True
        logger.info(f"🚀 持仓监控服务启动 (检查间隔: {self.check_interval}秒)")

        while self.running:
            try:
                self.check_and_execute()
                time.sleep(self.check_interval)
            except KeyboardInterrupt:
                logger.info("⏸️  收到停止信号")
                break
            except Exception as e:
                logger.exception(f"❌ 监控循环异常: {e}")
                time.sleep(self.check_interval)

        logger.info("🛑 持仓监控服务已停止")

    def stop(self):
        """停止监控"""
        self.running = False


def main():
    """主函数 - 独立运行监控服务"""
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/tmp/position_monitor.log')
        ]
    )

    load_dotenv()

    # 初始化 OKX 客户端
    from perpbot.exchanges.okx import OKXClient

    okx_env = os.getenv("OKX_ENV", "testnet").lower()
    use_testnet = okx_env in ["testnet", "test"]

    logger.info(f"初始化 OKX 客户端 (use_testnet={use_testnet})")
    okx = OKXClient(use_testnet=use_testnet, allow_mainnet=True)
    okx.connect()

    if not okx._trading_enabled:
        logger.error("❌ OKX 交易未启用，请检查 API 凭据")
        sys.exit(1)

    logger.info("✅ OKX 客户端已连接")

    # 创建监控器
    check_interval = float(os.getenv("POSITION_MONITOR_INTERVAL", "5.0"))
    monitor = PositionMonitor(okx, check_interval=check_interval)

    # 启动监控
    try:
        monitor.run()
    except KeyboardInterrupt:
        logger.info("停止中...")
        monitor.stop()


if __name__ == "__main__":
    main()
