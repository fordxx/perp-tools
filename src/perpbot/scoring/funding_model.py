"""
FundingModel - 资金费率模型

支持：
- 获取每个交易所每个合约的下一期 funding rate
- 不同结算周期（8h / 4h / 1h）
- 预测未来资金费率收益
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple


logger = logging.getLogger(__name__)


@dataclass
class FundingRateInfo:
    """资金费率信息"""
    exchange: str
    symbol: str
    current_rate: float          # 当前费率
    next_funding_time: datetime  # 下一次结算时间
    interval_hours: float        # 结算间隔（小时）


class FundingModel:
    """
    资金费率模型

    管理所有交易所的资金费率，预测收益
    """

    # 各交易所默认结算周期
    DEFAULT_INTERVALS = {
        "binance": 8.0,   # 8小时
        "okx": 8.0,
        "bybit": 8.0,
        "edgex": 4.0,     # 4小时（假设）
        "ftx": 1.0,       # 1小时（已下线，仅示例）
    }

    def __init__(self):
        """初始化资金费率模型"""
        # 存储实时费率数据
        # {(exchange, symbol): FundingRateInfo}
        self.funding_rates: Dict[Tuple[str, str], FundingRateInfo] = {}

        logger.info("初始化资金费率模型")

    def update_funding_rate(
        self,
        exchange: str,
        symbol: str,
        current_rate: float,
        next_funding_time: Optional[datetime] = None,
    ):
        """
        更新资金费率

        Args:
            exchange: 交易所
            symbol: 交易对
            current_rate: 当前费率（小数，如 0.0001 表示 0.01%）
            next_funding_time: 下一次结算时间（如果为 None 则自动计算）
        """
        interval_hours = self.get_funding_interval_hours(exchange)

        if next_funding_time is None:
            # 自动计算下一次结算时间（简化）
            now = datetime.utcnow()
            # 假设每天固定时间结算（0:00, 8:00, 16:00）
            hours_since_midnight = now.hour
            next_settlement_hour = (
                (hours_since_midnight // int(interval_hours) + 1) * int(interval_hours)
            ) % 24
            next_funding_time = now.replace(
                hour=next_settlement_hour,
                minute=0,
                second=0,
                microsecond=0
            )
            if next_settlement_hour <= now.hour:
                next_funding_time += timedelta(days=1)

        info = FundingRateInfo(
            exchange=exchange,
            symbol=symbol,
            current_rate=current_rate,
            next_funding_time=next_funding_time,
            interval_hours=interval_hours,
        )

        self.funding_rates[(exchange, symbol)] = info

        logger.debug(
            f"更新资金费率: {exchange} {symbol}, "
            f"rate={current_rate*10000:.2f}bps, "
            f"next={next_funding_time.isoformat()}"
        )

    def get_next_funding_rate(
        self,
        exchange: str,
        symbol: str,
    ) -> float:
        """
        获取下一期资金费率

        Args:
            exchange: 交易所
            symbol: 交易对

        Returns:
            资金费率（小数）
        """
        key = (exchange, symbol)
        info = self.funding_rates.get(key)

        if not info:
            logger.warning(
                f"资金费率未配置: {exchange} {symbol}，返回 0"
            )
            return 0.0

        return info.current_rate

    def get_funding_interval_hours(self, exchange: str) -> float:
        """
        获取资金费率结算间隔

        Args:
            exchange: 交易所

        Returns:
            间隔小时数
        """
        return self.DEFAULT_INTERVALS.get(exchange, 8.0)

    def calculate_funding_pnl(
        self,
        exchange: str,
        symbol: str,
        notional: float,
        position_side: str,  # "long" or "short"
        holding_hours: float = 8.0,
    ) -> float:
        """
        计算资金费率收益

        Args:
            exchange: 交易所
            symbol: 交易对
            notional: 持仓名义金额
            position_side: 持仓方向（"long" 或 "short"）
            holding_hours: 持仓时长（小时）

        Returns:
            资金费率收益（正数=收入，负数=支出）
        """
        rate = self.get_next_funding_rate(exchange, symbol)
        interval_hours = self.get_funding_interval_hours(exchange)

        # 计算期数
        num_periods = holding_hours / interval_hours

        # 计算总收益
        # 如果 rate > 0（多头支付空头），持有空头赚钱
        # 如果 rate < 0（空头支付多头），持有多头赚钱
        if position_side == "long":
            # 多头支付资金费率
            pnl = -rate * notional * num_periods
        elif position_side == "short":
            # 空头收取资金费率
            pnl = rate * notional * num_periods
        else:
            raise ValueError(f"Invalid position_side: {position_side}")

        logger.debug(
            f"资金费率收益: {exchange} {symbol}, "
            f"notional={notional:.0f}, side={position_side}, "
            f"rate={rate*10000:.2f}bps, periods={num_periods:.2f}, "
            f"pnl={pnl:.4f}"
        )

        return pnl

    def calculate_arbitrage_funding_pnl(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        notional: float,
        holding_hours: float = 8.0,
    ) -> float:
        """
        计算套利资金费率收益（买入 = 多头，卖出 = 空头）

        Args:
            buy_exchange: 买入交易所
            sell_exchange: 卖出交易所
            symbol: 交易对
            notional: 名义金额
            holding_hours: 持仓时长

        Returns:
            净资金费率收益
        """
        # 买入方（多头）支付资金费率
        buy_pnl = self.calculate_funding_pnl(
            buy_exchange, symbol, notional, "long", holding_hours
        )

        # 卖出方（空头）收取资金费率
        sell_pnl = self.calculate_funding_pnl(
            sell_exchange, symbol, notional, "short", holding_hours
        )

        # 净收益
        total_pnl = buy_pnl + sell_pnl

        logger.debug(
            f"套利资金费率: {buy_exchange}<->{sell_exchange} {symbol}, "
            f"buy_pnl={buy_pnl:.4f}, sell_pnl={sell_pnl:.4f}, "
            f"total={total_pnl:.4f}"
        )

        return total_pnl

    def get_time_to_next_funding(
        self,
        exchange: str,
        symbol: str,
    ) -> Optional[float]:
        """
        获取距离下一次结算的时间

        Args:
            exchange: 交易所
            symbol: 交易对

        Returns:
            小时数（None 如果未配置）
        """
        key = (exchange, symbol)
        info = self.funding_rates.get(key)

        if not info:
            return None

        delta = info.next_funding_time - datetime.utcnow()
        return delta.total_seconds() / 3600.0

    def is_funding_favorable(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
    ) -> bool:
        """
        判断资金费率是否有利于套利

        有利条件：
        - buy_exchange 的 funding rate 为负（多头收钱）
        - sell_exchange 的 funding rate 为正（空头收钱）
        - 或者至少净收益为正

        Args:
            buy_exchange: 买入交易所
            sell_exchange: 卖出交易所
            symbol: 交易对

        Returns:
            是否有利
        """
        buy_rate = self.get_next_funding_rate(buy_exchange, symbol)
        sell_rate = self.get_next_funding_rate(sell_exchange, symbol)

        # 买入（多头）支付 buy_rate
        # 卖出（空头）收取 sell_rate
        # 净收益 = sell_rate - buy_rate
        net_rate = sell_rate - buy_rate

        return net_rate > 0

    def get_all_funding_rates(self) -> Dict[Tuple[str, str], FundingRateInfo]:
        """获取所有资金费率信息"""
        return self.funding_rates.copy()

    def clear_expired_rates(self):
        """清除过期的资金费率数据"""
        now = datetime.utcnow()
        expired = []

        for key, info in self.funding_rates.items():
            if info.next_funding_time < now:
                expired.append(key)

        for key in expired:
            del self.funding_rates[key]
            logger.debug(f"清除过期资金费率: {key}")

        if expired:
            logger.info(f"清除了 {len(expired)} 个过期资金费率")
