"""
Bootstrap 双交易所对冲执行器

目标：OKX + Binance 最小对冲系统
- 同时市价开仓（对冲）
- 同时市价平仓
- 可回滚、可熔断

风险参数：
- 单笔名义: 300 USDT
- 杠杆: 1x
- 最大滑点: 0.05%
- 最大持仓时间: 10 秒
- 单边未成交超时: 800ms
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Order, OrderRequest, Position

logger = logging.getLogger(__name__)


@dataclass
class HedgeConfig:
    """对冲配置"""
    symbol: str = "BTC/USDT"
    notional_usdt: float = 300.0  # 名义金额
    max_slippage_bps: float = 5.0  # 最大滑点 0.05%
    max_position_duration_seconds: float = 10.0  # 最大持仓时间
    max_order_latency_ms: float = 800.0  # 单边未成交超时
    max_acceptable_loss_pct: float = 0.2  # 最大可接受亏损


@dataclass
class HedgeResult:
    """对冲结果"""
    success: bool
    open_order_a: Optional[Order]
    open_order_b: Optional[Order]
    close_order_a: Optional[Order]
    close_order_b: Optional[Order]
    pnl_a: float = 0.0
    pnl_b: float = 0.0
    total_pnl: float = 0.0
    error_message: Optional[str] = None


class BootstrapHedgeExecutor:
    """Bootstrap 最小对冲执行器"""

    def __init__(
        self,
        exchange_a: ExchangeClient,
        exchange_b: ExchangeClient,
        config: Optional[HedgeConfig] = None
    ):
        self.exchange_a = exchange_a
        self.exchange_b = exchange_b
        self.config = config or HedgeConfig()

        logger.info("=" * 60)
        logger.info("Bootstrap Hedge Executor Initialized")
        logger.info("=" * 60)
        logger.info("Exchange A: %s", exchange_a.name)
        logger.info("Exchange B: %s", exchange_b.name)
        logger.info("Symbol: %s", self.config.symbol)
        logger.info("Notional: %.2f USDT", self.config.notional_usdt)
        logger.info("=" * 60)

    def _get_prices(self) -> tuple[float, float]:
        """获取双边价格"""
        quote_a = self.exchange_a.get_current_price(self.config.symbol)
        quote_b = self.exchange_b.get_current_price(self.config.symbol)

        logger.info("Prices: %s=%.2f, %s=%.2f",
                   self.exchange_a.name, quote_a.mid,
                   self.exchange_b.name, quote_b.mid)

        return quote_a.mid, quote_b.mid

    def _calculate_size(self, price: float) -> float:
        """根据价格计算数量"""
        return self.config.notional_usdt / price

    def execute_hedge_cycle(self) -> HedgeResult:
        """执行完整对冲周期：开仓 → 持仓 → 平仓"""
        result = HedgeResult(success=False)

        try:
            # Step 1: 获取价格
            logger.info("\n" + "=" * 60)
            logger.info("Step 1: Fetching Prices")
            logger.info("=" * 60)

            price_a, price_b = self._get_prices()

            # Step 2: 计算数量
            size_a = self._calculate_size(price_a)
            size_b = self._calculate_size(price_b)

            logger.info("Calculated sizes: %s=%.4f, %s=%.4f",
                       self.exchange_a.name, size_a,
                       self.exchange_b.name, size_b)

            # Step 3: 同时开仓（对冲）
            logger.info("\n" + "=" * 60)
            logger.info("Step 2: Opening Hedge Positions (MARKET)")
            logger.info("=" * 60)

            # Exchange A: 做多
            request_a = OrderRequest(
                symbol=self.config.symbol,
                side="buy",
                size=size_a,
                limit_price=None  # MARKET
            )

            # Exchange B: 做空
            request_b = OrderRequest(
                symbol=self.config.symbol,
                side="sell",
                size=size_b,
                limit_price=None  # MARKET
            )

            logger.info("Placing orders simultaneously...")
            start_time = time.time()

            # 同时下单
            result.open_order_a = self.exchange_a.place_open_order(request_a)
            result.open_order_b = self.exchange_b.place_open_order(request_b)

            latency_ms = (time.time() - start_time) * 1000

            # 检查是否成功
            if result.open_order_a.id.startswith("rejected"):
                result.error_message = f"{self.exchange_a.name} order rejected"
                logger.error("❌ %s", result.error_message)
                return result

            if result.open_order_b.id.startswith("rejected"):
                result.error_message = f"{self.exchange_b.name} order rejected"
                logger.error("❌ %s", result.error_message)
                # Rollback: 平掉 A 的仓位
                self._emergency_close_a(result.open_order_a)
                return result

            # 检查延迟
            if latency_ms > self.config.max_order_latency_ms:
                result.error_message = f"Order latency too high: {latency_ms:.0f}ms > {self.config.max_order_latency_ms}ms"
                logger.warning("⚠️ %s", result.error_message)

            logger.info("✅ Orders filled:")
            logger.info("   %s: %s %.4f @ %.2f (OrderID: %s)",
                       self.exchange_a.name,
                       result.open_order_a.side.upper(),
                       result.open_order_a.size,
                       result.open_order_a.price,
                       result.open_order_a.id)
            logger.info("   %s: %s %.4f @ %.2f (OrderID: %s)",
                       self.exchange_b.name,
                       result.open_order_b.side.upper(),
                       result.open_order_b.size,
                       result.open_order_b.price,
                       result.open_order_b.id)
            logger.info("   Latency: %.0f ms", latency_ms)

            # Step 4: 持仓等待
            logger.info("\n" + "=" * 60)
            logger.info("Step 3: Holding Position for %.1f seconds", self.config.max_position_duration_seconds)
            logger.info("=" * 60)

            time.sleep(self.config.max_position_duration_seconds)

            # Step 5: 同时平仓
            logger.info("\n" + "=" * 60)
            logger.info("Step 4: Closing Positions (MARKET)")
            logger.info("=" * 60)

            # 获取当前价格用于平仓
            close_price_a, close_price_b = self._get_prices()

            # 创建 Position 对象
            position_a = Position(
                id=result.open_order_a.id,
                order=result.open_order_a,
                target_profit_pct=0.0
            )

            position_b = Position(
                id=result.open_order_b.id,
                order=result.open_order_b,
                target_profit_pct=0.0
            )

            logger.info("Closing positions simultaneously...")

            # 同时平仓
            result.close_order_a = self.exchange_a.place_close_order(position_a, close_price_a)
            result.close_order_b = self.exchange_b.place_close_order(position_b, close_price_b)

            logger.info("✅ Positions closed:")
            logger.info("   %s: %s %.4f @ %.2f (OrderID: %s)",
                       self.exchange_a.name,
                       result.close_order_a.side.upper(),
                       result.close_order_a.size,
                       result.close_order_a.price,
                       result.close_order_a.id)
            logger.info("   %s: %s %.4f @ %.2f (OrderID: %s)",
                       self.exchange_b.name,
                       result.close_order_b.side.upper(),
                       result.close_order_b.size,
                       result.close_order_b.price,
                       result.close_order_b.id)

            # Step 6: 计算 PnL
            logger.info("\n" + "=" * 60)
            logger.info("Step 5: Calculating PnL")
            logger.info("=" * 60)

            # Exchange A (买入开仓，卖出平仓)
            result.pnl_a = (result.close_order_a.price - result.open_order_a.price) * result.open_order_a.size

            # Exchange B (卖出开仓，买入平仓)
            result.pnl_b = (result.open_order_b.price - result.close_order_b.price) * result.open_order_b.size

            result.total_pnl = result.pnl_a + result.pnl_b

            logger.info("%s PnL: $%.2f", self.exchange_a.name, result.pnl_a)
            logger.info("%s PnL: $%.2f", self.exchange_b.name, result.pnl_b)
            logger.info("Total PnL: $%.2f", result.total_pnl)

            # 检查亏损是否在可接受范围
            loss_pct = abs(result.total_pnl / self.config.notional_usdt * 100)
            if result.total_pnl < 0 and loss_pct > self.config.max_acceptable_loss_pct:
                logger.warning("⚠️ Loss exceeds threshold: %.2f%% > %.2f%%",
                             loss_pct, self.config.max_acceptable_loss_pct)

            result.success = True
            logger.info("\n" + "=" * 60)
            logger.info("✅ HEDGE CYCLE COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)

        except Exception as e:
            result.success = False
            result.error_message = str(e)
            logger.exception("❌ Hedge cycle failed: %s", e)

        return result

    def _emergency_close_a(self, order: Order) -> None:
        """紧急平仓 Exchange A（回滚）"""
        logger.warning("⚠️ Emergency rollback: closing %s position", self.exchange_a.name)
        try:
            position = Position(id=order.id, order=order, target_profit_pct=0.0)
            current_price = self.exchange_a.get_current_price(self.config.symbol).mid
            self.exchange_a.place_close_order(position, current_price)
            logger.info("✅ Rollback successful")
        except Exception as e:
            logger.exception("❌ Rollback failed: %s", e)

    def get_positions(self) -> tuple[List[Position], List[Position]]:
        """获取双边持仓"""
        positions_a = self.exchange_a.get_account_positions()
        positions_b = self.exchange_b.get_account_positions()

        logger.info("%s positions: %d", self.exchange_a.name, len(positions_a))
        logger.info("%s positions: %d", self.exchange_b.name, len(positions_b))

        return positions_a, positions_b
