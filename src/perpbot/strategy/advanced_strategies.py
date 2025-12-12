"""增强策略模块

包含多种交易策略：
- TakeProfitStrategy: 基础止盈策略
- TrailingStopStrategy: 追踪止损/止盈策略
- GridTradingStrategy: 网格交易策略
- DynamicPositionStrategy: 动态仓位管理
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Order, OrderRequest, Position, PriceQuote, TradingState

logger = logging.getLogger(__name__)


class TakeProfitStrategy:
    """基础止盈策略 - 到达目标利润后自动平仓"""

    def __init__(self, profit_target_pct: float = 0.01):
        self.target = profit_target_pct

    def open_position(self, exchange: ExchangeClient, quote: PriceQuote, size: float, side: str) -> Position:
        order_req = OrderRequest(symbol=quote.symbol, side=side, size=size, limit_price=quote.mid)
        order = exchange.place_order(order_req)
        return Position(id=order.id, order=order, target_profit_pct=self.target)

    def evaluate_positions(self, state: TradingState, quotes: Iterable[PriceQuote], exchanges: List[ExchangeClient]) -> List[Order]:
        closed: List[Order] = []
        quote_map = {q.exchange: q for q in quotes}
        for pos_id, position in list(state.open_positions.items()):
            if not position.is_open():
                continue
            quote = quote_map.get(position.order.exchange)
            if not quote:
                continue
            pnl_pct = (quote.mid - position.order.price) / position.order.price
            if position.order.side == "sell":
                pnl_pct *= -1
            if pnl_pct >= position.target_profit_pct:
                ex = next(ex for ex in exchanges if ex.name == position.order.exchange)
                close_order = ex.close_position(position, quote.mid)
                position.closed_ts = close_order.created_at
                closed.append(close_order)
                del state.open_positions[pos_id]
        return closed

    def maybe_trade(self, state: TradingState, exchange: ExchangeClient, signal: float, quote: PriceQuote, size: float) -> Position | None:
        if abs(signal) < 0.5:
            return None
        side = "buy" if signal > 0 else "sell"
        position = self.open_position(exchange, quote, size=size, side=side)
        state.open_positions[position.id] = position
        return position


@dataclass
class TrailingStopConfig:
    """追踪止损配置"""
    activation_pct: float = 0.005  # 激活追踪的利润百分比
    trailing_pct: float = 0.003   # 回撤触发平仓的百分比
    max_loss_pct: float = 0.02    # 最大止损百分比


class TrailingStopStrategy:
    """追踪止损策略 - 利润达到激活点后开始追踪，回撤到一定比例时平仓"""

    def __init__(self, config: TrailingStopConfig = None):
        self.config = config or TrailingStopConfig()
        # 记录每个持仓的最高利润点
        self.high_water_marks: Dict[str, float] = {}

    def update_position(self, position: Position, current_price: float) -> tuple[bool, str]:
        """
        更新持仓状态，返回 (是否应该平仓, 原因)
        """
        entry_price = position.order.price
        side = position.order.side

        # 计算当前 PnL
        if side == "buy":
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price

        # 止损检查
        if pnl_pct <= -self.config.max_loss_pct:
            return True, f"止损: {pnl_pct:.2%}"

        # 更新最高点
        pos_id = position.id
        if pos_id not in self.high_water_marks:
            self.high_water_marks[pos_id] = pnl_pct
        else:
            self.high_water_marks[pos_id] = max(self.high_water_marks[pos_id], pnl_pct)

        high_pnl = self.high_water_marks[pos_id]

        # 检查是否激活追踪
        if high_pnl >= self.config.activation_pct:
            drawdown = high_pnl - pnl_pct
            if drawdown >= self.config.trailing_pct:
                return True, f"追踪止盈: 最高{high_pnl:.2%}, 回撤{drawdown:.2%}"

        return False, ""

    def evaluate_positions(
        self,
        state: TradingState,
        quotes: Iterable[PriceQuote],
        exchanges: List[ExchangeClient],
    ) -> List[Order]:
        closed: List[Order] = []
        quote_map = {(q.exchange, q.symbol): q for q in quotes}

        for pos_id, position in list(state.open_positions.items()):
            if not position.is_open():
                continue

            key = (position.order.exchange, position.order.symbol)
            quote = quote_map.get(key)
            if not quote:
                continue

            should_close, reason = self.update_position(position, quote.mid)
            if should_close:
                ex = next((ex for ex in exchanges if ex.name == position.order.exchange), None)
                if ex:
                    logger.info("🔔 %s: %s", position.order.symbol, reason)
                    close_order = ex.close_position(position, quote.mid)
                    position.closed_ts = close_order.created_at
                    closed.append(close_order)
                    del state.open_positions[pos_id]
                    # 清理记录
                    if pos_id in self.high_water_marks:
                        del self.high_water_marks[pos_id]

        return closed


@dataclass
class GridLevel:
    """网格级别"""
    price: float
    side: str  # "buy" or "sell"
    size: float
    order_id: Optional[str] = None
    filled: bool = False


@dataclass
class GridConfig:
    """网格配置"""
    upper_price: float          # 网格上限
    lower_price: float          # 网格下限
    grid_count: int = 10        # 网格数量
    total_size: float = 1.0     # 总仓位大小
    take_profit_pct: float = 0.001  # 每格止盈


class GridTradingStrategy:
    """网格交易策略 - 在价格区间内自动挂单"""

    def __init__(self, config: GridConfig):
        self.config = config
        self.grids: List[GridLevel] = []
        self.initialized = False

    def initialize_grids(self, current_price: float) -> List[GridLevel]:
        """根据当前价格初始化网格"""
        grids = []
        price_range = self.config.upper_price - self.config.lower_price
        grid_size = price_range / self.config.grid_count
        size_per_grid = self.config.total_size / self.config.grid_count

        for i in range(self.config.grid_count + 1):
            price = self.config.lower_price + i * grid_size
            # 低于当前价的设为买单，高于当前价的设为卖单
            side = "buy" if price < current_price else "sell"
            grids.append(GridLevel(
                price=round(price, 2),
                side=side,
                size=size_per_grid,
            ))

        self.grids = grids
        self.initialized = True
        logger.info(f"📊 初始化 {len(grids)} 个网格: {self.config.lower_price} - {self.config.upper_price}")
        return grids

    def get_pending_orders(self, current_price: float) -> List[GridLevel]:
        """获取需要下单的网格"""
        if not self.initialized:
            self.initialize_grids(current_price)

        pending = []
        for grid in self.grids:
            if grid.order_id or grid.filled:
                continue
            # 只返回合理的挂单
            if grid.side == "buy" and grid.price < current_price * 0.999:
                pending.append(grid)
            elif grid.side == "sell" and grid.price > current_price * 1.001:
                pending.append(grid)

        return pending

    def mark_filled(self, order_id: str):
        """标记订单已成交"""
        for grid in self.grids:
            if grid.order_id == order_id:
                grid.filled = True
                # 在相邻格子创建反向单
                logger.info(f"🎯 网格成交: {grid.side} @ {grid.price}")
                break

    def place_grid_orders(self, exchange: ExchangeClient, current_price: float) -> List[Order]:
        """下网格订单"""
        orders = []
        pending = self.get_pending_orders(current_price)

        for grid in pending[:5]:  # 每次最多下5个
            try:
                order_req = OrderRequest(
                    symbol="ETH/USDT",  # TODO: 配置化
                    side=grid.side,
                    size=grid.size,
                    limit_price=grid.price,
                )
                order = exchange.place_open_order(order_req)
                grid.order_id = order.id
                orders.append(order)
                logger.info(f"📝 网格下单: {grid.side} {grid.size} @ {grid.price}")
            except Exception as e:
                logger.error(f"网格下单失败: {e}")

        return orders


@dataclass
class PositionSizeConfig:
    """动态仓位配置"""
    base_size: float = 0.01       # 基础仓位
    max_size: float = 0.1         # 最大仓位
    win_multiplier: float = 1.2   # 盈利时仓位乘数
    loss_multiplier: float = 0.8  # 亏损时仓位乘数
    max_consecutive_losses: int = 3  # 最大连续亏损次数


class DynamicPositionStrategy:
    """动态仓位管理 - 根据盈亏调整仓位大小"""

    def __init__(self, config: PositionSizeConfig = None):
        self.config = config or PositionSizeConfig()
        self.current_size = self.config.base_size
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.trade_history: List[tuple[datetime, float]] = []  # (时间, PnL)

    def record_trade(self, pnl: float):
        """记录交易结果"""
        self.trade_history.append((datetime.utcnow(), pnl))

        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            # 盈利后增加仓位
            self.current_size = min(
                self.current_size * self.config.win_multiplier,
                self.config.max_size,
            )
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            # 亏损后减少仓位
            self.current_size = max(
                self.current_size * self.config.loss_multiplier,
                self.config.base_size * 0.5,  # 最小为基础的一半
            )

        logger.info(f"📊 仓位调整: {self.current_size:.4f} (连赢{self.consecutive_wins}/连亏{self.consecutive_losses})")

    def get_position_size(self) -> float:
        """获取当前建议仓位大小"""
        # 如果连续亏损太多，暂停交易
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            logger.warning(f"⚠️ 连续亏损 {self.consecutive_losses} 次，建议暂停交易")
            return 0.0

        return self.current_size

    def should_pause(self) -> bool:
        """是否应该暂停交易"""
        return self.consecutive_losses >= self.config.max_consecutive_losses

    def reset(self):
        """重置仓位到基础值"""
        self.current_size = self.config.base_size
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        logger.info("🔄 仓位已重置")

    def get_stats(self) -> dict:
        """获取统计信息"""
        if not self.trade_history:
            return {"total_trades": 0}

        wins = sum(1 for _, pnl in self.trade_history if pnl > 0)
        losses = sum(1 for _, pnl in self.trade_history if pnl <= 0)
        total_pnl = sum(pnl for _, pnl in self.trade_history)

        return {
            "total_trades": len(self.trade_history),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(self.trade_history) if self.trade_history else 0,
            "total_pnl": total_pnl,
            "current_size": self.current_size,
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
        }
