from __future__ import annotations
from typing import Dict, List, Optional

from .pair_scanner import PairScanner, SpreadResult
from .scanner_config import ScannerConfig


class MarketScannerV3:
    def __init__(self, config: ScannerConfig, quote_engine):
        self.config = config
        self.pair_scanner = PairScanner(config)
        self.quote_engine = quote_engine
        self.exchanges: List[str] = []
        self.symbols: List[str] = []

    def set_exchanges(self, exchanges: List[str]):
        self.exchanges = exchanges

    def set_symbols(self, symbols: List[str]):
        self.symbols = symbols

    def scan_once(self) -> List[SpreadResult]:
        """
        扫描所有 symbol × (exchange pair)
        返回套利结果列表
        """
        results: List[SpreadResult] = []

        for symbol in self.symbols:
            mid_book = self.quote_engine.get_bbo(symbol)
            if not mid_book:
                continue

            bids = {}
            asks = {}
            for exchange in self.exchanges:
                bbo = self.quote_engine.get_bbo(symbol)
                if not bbo:
                    continue
                bids[exchange] = bbo[0]
                asks[exchange] = bbo[1]

            for idx_a, exchange_a in enumerate(self.exchanges):
                for exchange_b in self.exchanges[idx_a + 1:]:
                    if exchange_a not in bids or exchange_b not in bids:
                        continue

                    spread = self.pair_scanner.scan(
                        symbol=symbol,
                        bbo_a=(bids[exchange_a], asks[exchange_a]),
                        bbo_b=(bids[exchange_b], asks[exchange_b]),
                        latency_a=0.0,
                        latency_b=0.0,
                        quality_a=0.0,
                        quality_b=0.0,
                        exchange_a=exchange_a,
                        exchange_b=exchange_b,
                    )
                    if spread:
                        results.append(spread)

        return results
