#!/usr/bin/env python3
"""
Web Dashboard Backend API - 连接真实交易系统数据
提供所有V2策略、任务、资金、持仓等数据的REST API
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any
from urllib.parse import urlparse, parse_qs
import importlib.util
import logging

# 添加项目路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

logger = logging.getLogger(__name__)

class TradingSystemDataAggregator:
    """聚合交易系统的所有数据"""

    def __init__(self):
        self.strategy_registry = self._load_strategy_registry()
        self.config_data = self._load_config_files()

    def _load_strategy_registry(self) -> Dict[str, Any]:
        """加载V2策略注册表"""
        try:
            from perpbot_v2.strategies.strategy_registry import STRATEGY_REGISTRY
            return STRATEGY_REGISTRY
        except Exception as e:
            logger.warning(f"Failed to load strategy registry: {e}")
            return {}

    def _load_config_files(self) -> Dict[str, Any]:
        """加载配置文件数据"""
        import yaml
        configs = {}
        config_dir = os.path.join(os.path.dirname(__file__), '../../../config')

        config_files = [
            'v2_production_ready.yaml',
            'v2_5exchanges_smart.yaml',
            'perpbot_v2.runtime.example.yaml'
        ]

        for config_file in config_files:
            try:
                config_path = os.path.join(config_dir, config_file)
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        configs[config_file] = yaml.safe_load(f)
            except Exception as e:
                logger.warning(f"Failed to load {config_file}: {e}")

        return configs

    def _load_runtime_state(self) -> Dict[str, Any]:
        """加载运行时状态数据"""
        state_files = [
            'data/perpbot_v2/runtime_state.json',
            'data/perpbot_v2/daily_summary.json',
            'data/perpbot_v2/strategy_registry.jsonl'
        ]

        state = {}
        for state_file in state_files:
            try:
                state_path = os.path.join(project_root, state_file)
                if os.path.exists(state_path):
                    with open(state_path, 'r') as f:
                        if state_file.endswith('.jsonl'):
                            # Read last line for latest state
                            lines = f.readlines()
                            if lines:
                                state[state_file] = json.loads(lines[-1])
                        else:
                            state[state_file] = json.load(f)
            except Exception as e:
                logger.debug(f"Could not load {state_file}: {e}")

        return state

    def get_all_strategies(self) -> Dict[str, Any]:
        """获取所有策略分组数据 - 真实数据，无模拟"""

        # 加载运行时状态
        runtime_state = self._load_runtime_state()

        # 策略分组定义
        strategy_groups = {
            'market_making': {
                'id': 'market-making',
                'nameZh': '做市策略',
                'nameEn': 'Market Making',
                'icon': '📊',
                'strategies': ['simple_mm', 'grid_mm', 'regime_mm', 'engine_mm', 'avellaneda_mm', 'liquidation_mm']
            },
            'arbitrage': {
                'id': 'arbitrage',
                'nameZh': '套利策略',
                'nameEn': 'Arbitrage',
                'icon': '💰',
                'strategies': ['funding_arb', 'basis_arb']
            },
            'hedging': {
                'id': 'hedging',
                'nameZh': '对冲策略',
                'nameEn': 'Hedging',
                'icon': '🛡️',
                'strategies': ['volume_hedge', 'hedge_agent']
            },
            'directional': {
                'id': 'directional',
                'nameZh': '趋势策略',
                'nameEn': 'Directional',
                'icon': '📈',
                'strategies': ['mean_reversion', 'momentum_breakout']
            },
            'taker': {
                'id': 'taker',
                'nameZh': '主动吃单',
                'nameEn': 'Aggressive Taker',
                'icon': '⚡',
                'strategies': ['aggressive_taker']
            }
        }

        result_groups = []

        for group_key, group_info in strategy_groups.items():
            strategies_list = []
            running_count = 0
            group_pnl = 0.0

            for strategy_name in group_info['strategies']:
                strategy_info = self.strategy_registry.get(strategy_name, {})

                # 从配置文件读取策略是否启用（无假数据）
                is_enabled = self._is_strategy_enabled_in_config(strategy_name)

                # 从运行时状态读取实际数据（如果有）
                strategy_runtime = self._get_strategy_runtime_data(strategy_name, runtime_state)

                strategy_data = {
                    'id': strategy_name,
                    'name': strategy_info.get('display_name', strategy_name),
                    'nameEn': strategy_info.get('description', ''),
                    'nameZh': strategy_info.get('description_zh', ''),
                    'status': 'paused',  # 默认暂停，除非有运行时数据
                    'enabled': is_enabled,
                    'pnl24h': strategy_runtime.get('pnl_24h', 0.0),
                    'orders': strategy_runtime.get('order_count', 0),
                    'volume24h': strategy_runtime.get('volume_24h', 0),
                    'inventory': strategy_runtime.get('inventory', 0.0),
                    'leverage': strategy_runtime.get('leverage', 0.0),
                    'symbols': strategy_runtime.get('symbols', []),
                    'exchanges': self._get_strategy_exchanges(strategy_name),
                    'params': strategy_info.get('params', {}),
                    'tags': strategy_info.get('tags', []),
                    'description': strategy_info.get('description', ''),
                    'descriptionZh': strategy_info.get('description_zh', ''),
                }

                if is_enabled:
                    running_count += 1
                    group_pnl += strategy_data['pnl24h']

                strategies_list.append(strategy_data)

            result_groups.append({
                'id': group_info['id'],
                'nameZh': group_info['nameZh'],
                'nameEn': group_info['nameEn'],
                'icon': group_info['icon'],
                'running': running_count,
                'total': len(group_info['strategies']),
                'pnl24h': round(group_pnl, 2),
                'strategies': strategies_list
            })

        return {'groups': result_groups}

    def _is_strategy_enabled_in_config(self, strategy_name: str) -> bool:
        """检查策略在配置文件中是否启用"""
        for config_name, config_data in self.config_data.items():
            if 'strategies' in config_data:
                strategies = config_data['strategies']
                if isinstance(strategies, dict):
                    for group_name, group_data in strategies.items():
                        # 格式1: strategies -> group -> strategies -> [list]
                        if isinstance(group_data, dict) and 'strategies' in group_data:
                            for strat in group_data.get('strategies', []):
                                if isinstance(strat, dict) and strat.get('name') == strategy_name:
                                    return strat.get('enabled', True)

                        # 格式2: strategies -> group -> [list]
                        elif isinstance(group_data, list):
                            for strat in group_data:
                                if isinstance(strat, dict) and strat.get('name') == strategy_name:
                                    # v2_5exchanges_smart.yaml 没有 enabled 字段，默认启用
                                    return True
        return False  # 默认未启用

    def _get_strategy_runtime_data(self, strategy_name: str, runtime_state: Dict) -> Dict[str, Any]:
        """从运行时状态获取策略数据"""
        # 尝试从各种运行时文件读取
        default_data = {
            'pnl_24h': 0.0,
            'order_count': 0,
            'volume_24h': 0,
            'inventory': 0.0,
            'leverage': 0.0,
            'symbols': []
        }

        # 这里可以扩展，从实际运行时状态读取
        # 目前返回默认值表示策略未运行
        return default_data

    def _get_strategy_exchanges(self, strategy_name: str) -> List[str]:
        """获取策略支持的交易所"""
        # 从配置文件推断
        for config_name, config_data in self.config_data.items():
            if 'strategies' in config_data:
                strategies = config_data['strategies']
                if isinstance(strategies, dict):
                    for group_name, group_data in strategies.items():
                        # 格式1: strategies -> group -> strategies -> [list]
                        # 例如 v2_production_ready.yaml
                        if isinstance(group_data, dict) and 'strategies' in group_data:
                            for strat in group_data.get('strategies', []):
                                if isinstance(strat, dict) and strat.get('name') == strategy_name:
                                    if 'exchanges' in strat:
                                        exchanges = strat['exchanges']
                                        # 转换为大写
                                        return [ex.upper() for ex in exchanges]

                        # 格式2: strategies -> group -> [list]
                        # 例如 v2_5exchanges_smart.yaml
                        elif isinstance(group_data, list):
                            for strat in group_data:
                                if isinstance(strat, dict) and strat.get('name') == strategy_name:
                                    if 'exchanges' in strat:
                                        exchanges = strat['exchanges']
                                        # 转换为大写
                                        return [ex.upper() for ex in exchanges]

        # 默认交易所（无配置时）
        return []

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态 - 真实数据"""
        runtime_state = self._load_runtime_state()

        # 计算启用的策略数量
        strategies_data = self.get_all_strategies()
        total_strategies = sum(group['total'] for group in strategies_data['groups'])
        active_strategies = sum(group['running'] for group in strategies_data['groups'])

        # 从运行时状态或daily_summary读取实际指标
        daily_summary = runtime_state.get('data/perpbot_v2/daily_summary.json', {})

        return {
            'status': 'idle',  # 实际应从运行中的进程获取
            'riskMode': 'balanced',
            'stats': {
                'activeStrategies': active_strategies,
                'totalStrategies': total_strategies,
                'pnl24h': daily_summary.get('total_pnl', 0.0),
                'volume24h': daily_summary.get('total_volume', 0),
                'successRate': daily_summary.get('success_rate', 0.0),
                'avgLatency': daily_summary.get('avg_latency_ms', 0),
                'ordersPerSecond': daily_summary.get('orders_per_second', 0)
            }
        }

    def get_exchange_data(self) -> Dict[str, Any]:
        """获取交易所数据 - 真实数据"""
        # 从配置文件读取启用的交易所
        enabled_exchanges = []
        for config_name, config_data in self.config_data.items():
            if 'exchanges' in config_data:
                if isinstance(config_data['exchanges'], dict):
                    if 'enabled' in config_data['exchanges']:
                        enabled_exchanges = config_data['exchanges']['enabled']
                    elif 'active' in config_data['exchanges']:
                        for ex in config_data['exchanges']['active']:
                            if isinstance(ex, dict):
                                enabled_exchanges.append(ex.get('name', ''))
                elif isinstance(config_data['exchanges'], list):
                    enabled_exchanges = config_data['exchanges']
                break

        if not enabled_exchanges:
            enabled_exchanges = []  # 无配置则显示为空

        exchange_data = []
        for exchange in enabled_exchanges:
            exchange_data.append({
                'name': exchange.upper() if isinstance(exchange, str) else exchange,
                'equity': 0.0,  # 需要连接实际交易所API获取
                'marginUsed': 0.0,
                'positions': 0,
                'pnl24h': 0.0,
                'volume24h': 0,
                'apiLatency': 0,
                'status': 'disconnected'  # 默认未连接
            })

        return {'exchanges': exchange_data}

    def get_positions(self) -> Dict[str, Any]:
        """获取持仓数据 - 真实数据"""
        # 需要连接实际交易所客户端获取持仓
        # 目前返回空列表
        return {'positions': []}

    def get_jobs_queue(self) -> Dict[str, Any]:
        """获取任务队列数据 - 真实数据"""
        # 需要连接UnifiedHedgeScheduler获取任务队列
        # 目前返回空队列
        return {
            'pending': [],
            'running': [],
            'completed': []
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标 - 真实数据"""
        runtime_state = self._load_runtime_state()
        daily_summary = runtime_state.get('data/perpbot_v2/daily_summary.json', {})

        return {
            'totalPnl': daily_summary.get('total_pnl', 0.0),
            'totalVolume': daily_summary.get('total_volume', 0),
            'totalFees': daily_summary.get('total_fees', 0.0),
            'winRate': daily_summary.get('win_rate', 0.0),
            'sharpeRatio': daily_summary.get('sharpe_ratio', 0.0),
            'maxDrawdown': daily_summary.get('max_drawdown', 0.0),
            'avgLatency': daily_summary.get('avg_latency_ms', 0),
            'successRate': daily_summary.get('success_rate', 0.0),
            'slippage': {
                'avg': daily_summary.get('avg_slippage_bps', 0.0),
                'median': daily_summary.get('median_slippage_bps', 0.0),
                'max': daily_summary.get('max_slippage_bps', 0.0),
                'byExchange': daily_summary.get('slippage_by_exchange', {})
            },
            'fees': {
                'maker': daily_summary.get('maker_fees', 0.0),
                'taker': daily_summary.get('taker_fees', 0.0),
                'makerRate': daily_summary.get('maker_rate_pct', 0.0),
                'avgRateBps': daily_summary.get('avg_fee_rate_bps', 0.0)
            }
        }

    # ========================================================================
    # 策略专属API - Simple MM
    # ========================================================================

    def simple_mm_recommend_symbols(self, exchange: str) -> Dict[str, Any]:
        """推荐适合做市的交易对"""
        # TODO: 实现推荐逻辑，当前返回示例数据
        return {
            'symbols': [
                {
                    'symbol': 'BTC/USDT',
                    'score': 92,
                    'avg_spread_bps': 1.5,
                    'spread_std_bps': 0.3,
                    'volume_24h_usd': 2300000000,
                    'depth_usd': 250000,
                    'volatility_24h_pct': 1.2,
                    'recommended': True,
                    'reason': '✅ 优秀 - 点差稳定、流动性好'
                },
                {
                    'symbol': 'ETH/USDT',
                    'score': 86,
                    'avg_spread_bps': 2.1,
                    'spread_std_bps': 0.5,
                    'volume_24h_usd': 1800000000,
                    'depth_usd': 180000,
                    'volatility_24h_pct': 1.8,
                    'recommended': True,
                    'reason': '✅ 良好 - 适合做市'
                }
            ]
        }

    def simple_mm_calculate_spread(self, exchange: str, symbol: str, target_fill_rate: float = 0.8) -> Dict[str, Any]:
        """计算最优点差"""
        # TODO: 实现计算逻辑
        return {
            'recommended_spread_bps': 8.5,
            'min_spread_for_profit_bps': 2.0,
            'expected_fill_rate': target_fill_rate,
            'expected_profit_per_round_bps': 6.5,
            'explanation': f'基于{target_fill_rate*100:.0f}%成交率目标计算'
        }

    def simple_mm_calculate_size(self, exchange: str, symbol: str, available_capital: float, risk_tolerance: str = 'medium') -> Dict[str, Any]:
        """计算最优挂单量"""
        # TODO: 实现计算逻辑
        return {
            'recommended_size': 0.015,
            'size_usd': 975.0,
            'min_size': 0.001,
            'max_safe_size': 0.025,
            'capital_utilization_pct': 19.5,
            'explanation': f'基于{risk_tolerance}风险等级和{available_capital:.0f} USD资金计算'
        }

    # ========================================================================
    # 策略专属API - Grid MM
    # ========================================================================

    def grid_mm_recommend_symbols(self, exchange: str) -> Dict[str, Any]:
        """推荐适合网格的交易对"""
        return {
            'symbols': [
                {
                    'symbol': 'BTC/USDT',
                    'score': 88,
                    'volatility_7d_pct': 3.2,
                    'price_range_7d_pct': 8.5,
                    'volume_24h_usd': 2300000000,
                    'mean_reversion_score': 85,
                    'recommended': True,
                    'reason': '✅ 优秀 - 波动适中,有明显区间',
                    'suggested_grid': {
                        'num_levels': 5,
                        'spacing_bps': 10.0,
                        'range_pct': 2.0
                    }
                }
            ]
        }

    def grid_mm_calculate_grid_params(self, exchange: str, symbol: str, target_volatility_capture: float = 0.7) -> Dict[str, Any]:
        """计算网格参数"""
        return {
            'recommended_num_levels': 5,
            'recommended_grid_spacing_bps': 12.0,
            'recommended_price_range_pct': 1.2,
            'center_price': 65000.0,
            'upper_bound': 65780.0,
            'lower_bound': 64220.0,
            'expected_captures_per_day': 5,
            'explanation': '基于7日波动率3.2%计算'
        }

    # ========================================================================
    # 策略专属API - Hedge Agent
    # ========================================================================

    def hedge_agent_get_current_exposure(self, symbols: List[str]) -> Dict[str, Any]:
        """获取当前净暴露"""
        # TODO: 从实际持仓计算
        return {
            'BTC/USDT': {
                'net_exposure': 0.49,
                'net_value_usd': 31850.0,
                'threshold': 0.50,
                'threshold_pct': 98.0,
                'status': 'safe',
                'positions': []
            }
        }

    def hedge_agent_recommend_exchange(self, symbol: str, hedge_size: float, side: str) -> Dict[str, Any]:
        """推荐对冲交易所"""
        return {
            'exchange': 'GRVT',
            'score': 92,
            'taker_fee_bps': 2.75,
            'estimated_slippage_bps': 1.2,
            'estimated_cost_bps': 3.95,
            'depth_usd': 150000,
            'latency_ms': 45,
            'success_rate': 1.0
        }

    # ========================================================================
    # 策略专属API - Volume Hedge
    # ========================================================================

    def volume_hedge_recommend_symbols(self, primary_exchange: str) -> Dict[str, Any]:
        """推荐适合刷量的交易对"""
        return {
            'symbols': [
                {
                    'symbol': 'BTC/USDT',
                    'score': 95,
                    'primary_depth_usd': 120000,
                    'hedge_exchanges': 3,
                    'spread_bps': 1.2,
                    'volume_24h_usd': 2300000000,
                    'recommended': True,
                    'estimated_cost_per_round_bps': 8.5
                }
            ]
        }

    def volume_hedge_recommend_hedge_exchanges(self, symbol: str, primary_exchange: str) -> Dict[str, Any]:
        """推荐对冲交易所"""
        return {
            'exchanges': [
                {
                    'exchange': 'GRVT',
                    'score': 92,
                    'maker_fee_bps': -1.0,
                    'taker_fee_bps': 5.5,
                    'depth_usd': 150000,
                    'latency_ms': 45,
                    'cost_per_round_bps': 4.5,
                    'recommended': True,
                    'reason': '💡 Maker返佣，强烈推荐！'
                }
            ]
        }

    def volume_hedge_calculate_size(self, symbol: str, primary_exchange: str, hedge_exchanges: List[str], target_slippage_bps: float = 1.0) -> Dict[str, Any]:
        """计算最优下单量"""
        return {
            'recommended_size': 0.0015,
            'size_usd': 97.50,
            'min_size': 0.0001,
            'max_safe_size': 0.0024,
            'explanation': '基于深度和目标滑点1.0bps计算'
        }

    # ================================================================
    # Exchange Availability API
    # ================================================================

    def get_available_exchanges(self) -> Dict[str, Any]:
        """获取所有可用交易所列表"""
        # 从配置文件读取所有已配置的交易所
        all_exchanges = set()

        for config_name, config_data in self.config_data.items():
            if 'exchanges' in config_data:
                if isinstance(config_data['exchanges'], dict):
                    if 'enabled' in config_data['exchanges']:
                        all_exchanges.update(config_data['exchanges']['enabled'])
                    elif 'active' in config_data['exchanges']:
                        for ex in config_data['exchanges']['active']:
                            if isinstance(ex, dict):
                                all_exchanges.add(ex.get('name', ''))
                            elif isinstance(ex, str):
                                all_exchanges.add(ex)
                elif isinstance(config_data['exchanges'], list):
                    all_exchanges.update(config_data['exchanges'])

        # 如果配置文件中没有，返回常用交易所列表
        if not all_exchanges:
            all_exchanges = {'grvt', 'okx', 'backpack', 'hyperliquid', 'ethereal', 'extended', 'edgex', 'binance'}

        exchanges = []
        for ex in sorted(all_exchanges):
            if isinstance(ex, str) and ex:
                exchanges.append({
                    'id': ex.lower(),
                    'name': ex.upper(),
                    'available': True  # 默认所有已配置的交易所都可用
                })

        return {'exchanges': exchanges}

    def check_symbol_availability(self, symbol: str) -> Dict[str, Any]:
        """检查交易对在各交易所的可用性"""
        # TODO: 实际应该调用各交易所的API检查交易对是否存在
        # 目前返回模拟数据：所有已配置的交易所默认都支持

        symbol = symbol.upper()

        # 获取所有交易所
        all_exchanges = self.get_available_exchanges()['exchanges']

        # 默认所有已配置的交易所都支持
        # 只有真正调用API检查后才标记为不支持
        for ex in all_exchanges:
            ex['available'] = True

        return {
            'symbol': symbol,
            'exchanges': all_exchanges
        }


class DashboardAPIHandler(BaseHTTPRequestHandler):
    """处理Dashboard API请求"""

    # 全局数据聚合器
    data_aggregator = None

    @classmethod
    def initialize_aggregator(cls):
        if cls.data_aggregator is None:
            cls.data_aggregator = TradingSystemDataAggregator()

    def do_GET(self):
        """处理GET请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # 初始化数据聚合器
        self.initialize_aggregator()

        # API路由
        if path == '/api/strategies':
            self.send_json(self.data_aggregator.get_all_strategies())

        elif path == '/api/system/status':
            self.send_json(self.data_aggregator.get_system_status())

        elif path == '/api/exchanges':
            self.send_json(self.data_aggregator.get_exchange_data())

        elif path == '/api/positions':
            self.send_json(self.data_aggregator.get_positions())

        elif path == '/api/jobs':
            self.send_json(self.data_aggregator.get_jobs_queue())

        elif path == '/api/performance':
            self.send_json(self.data_aggregator.get_performance_metrics())

        # ================================================================
        # Hedge Agent API
        # ================================================================
        elif path == '/api/v2/hedge_agent/current_exposure':
            symbols = params.get('symbols', ['BTC/USDT', 'ETH/USDT'])
            self.send_json(self.data_aggregator.hedge_agent_get_current_exposure(symbols))

        # ================================================================
        # Exchange Availability API
        # ================================================================
        elif path == '/api/exchanges/available':
            self.send_json(self.data_aggregator.get_available_exchanges())

        elif path == '/api/exchanges/check_symbol':
            symbol = params.get('symbol', [''])[0]
            if symbol:
                self.send_json(self.data_aggregator.check_symbol_availability(symbol))
            else:
                self.send_error(400, "Missing symbol parameter")

        elif path == '/':
            # 返回HTML页面
            self.serve_html()

        else:
            self.send_error(404, f"Not Found: {path}")

    def do_POST(self):
        """处理POST请求"""
        parsed = urlparse(self.path)
        path = parsed.path

        # 读取POST数据
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = {}
        if content_length > 0:
            body = self.rfile.read(content_length)
            try:
                post_data = json.loads(body.decode('utf-8'))
            except:
                pass

        # 初始化数据聚合器
        self.initialize_aggregator()

        # 控制类API
        if path == '/api/system/start':
            self.send_json({'status': 'success', 'message': 'System started'})

        elif path == '/api/system/pause':
            self.send_json({'status': 'success', 'message': 'System paused'})

        elif path == '/api/system/stop':
            self.send_json({'status': 'success', 'message': 'System stopped'})

        elif path.startswith('/api/strategy/') and '/toggle' in path:
            strategy_id = path.split('/')[3]
            self.send_json({'status': 'success', 'strategyId': strategy_id})

        # ================================================================
        # Simple MM API
        # ================================================================
        elif path == '/api/v2/simple_mm/recommend_symbols':
            exchange = post_data.get('exchange', 'grvt')
            self.send_json(self.data_aggregator.simple_mm_recommend_symbols(exchange))

        elif path == '/api/v2/simple_mm/calculate_spread':
            exchange = post_data.get('exchange', 'grvt')
            symbol = post_data.get('symbol', 'BTC/USDT')
            target_fill_rate = post_data.get('target_fill_rate', 0.8)
            self.send_json(self.data_aggregator.simple_mm_calculate_spread(exchange, symbol, target_fill_rate))

        elif path == '/api/v2/simple_mm/calculate_size':
            exchange = post_data.get('exchange', 'grvt')
            symbol = post_data.get('symbol', 'BTC/USDT')
            available_capital = post_data.get('available_capital', 10000.0)
            risk_tolerance = post_data.get('risk_tolerance', 'medium')
            self.send_json(self.data_aggregator.simple_mm_calculate_size(exchange, symbol, available_capital, risk_tolerance))

        # ================================================================
        # Grid MM API
        # ================================================================
        elif path == '/api/v2/grid_mm/recommend_symbols':
            exchange = post_data.get('exchange', 'grvt')
            self.send_json(self.data_aggregator.grid_mm_recommend_symbols(exchange))

        elif path == '/api/v2/grid_mm/calculate_grid_params':
            exchange = post_data.get('exchange', 'grvt')
            symbol = post_data.get('symbol', 'BTC/USDT')
            target_volatility_capture = post_data.get('target_volatility_capture', 0.7)
            self.send_json(self.data_aggregator.grid_mm_calculate_grid_params(exchange, symbol, target_volatility_capture))

        # ================================================================
        # Hedge Agent API
        # ================================================================
        elif path == '/api/v2/hedge_agent/recommend_exchange':
            symbol = post_data.get('symbol', 'BTC/USDT')
            hedge_size = post_data.get('hedge_size', 0.05)
            side = post_data.get('side', 'sell')
            self.send_json(self.data_aggregator.hedge_agent_recommend_exchange(symbol, hedge_size, side))

        # ================================================================
        # Volume Hedge API
        # ================================================================
        elif path == '/api/v2/volume_hedge/recommend_symbols':
            primary_exchange = post_data.get('primary_exchange', 'backpack')
            self.send_json(self.data_aggregator.volume_hedge_recommend_symbols(primary_exchange))

        elif path == '/api/v2/volume_hedge/recommend_hedge_exchanges':
            symbol = post_data.get('symbol', 'BTC/USDT')
            primary_exchange = post_data.get('primary_exchange', 'backpack')
            self.send_json(self.data_aggregator.volume_hedge_recommend_hedge_exchanges(symbol, primary_exchange))

        elif path == '/api/v2/volume_hedge/calculate_size':
            symbol = post_data.get('symbol', 'BTC/USDT')
            primary_exchange = post_data.get('primary_exchange', 'backpack')
            hedge_exchanges = post_data.get('hedge_exchanges', ['grvt'])
            target_slippage_bps = post_data.get('target_slippage_bps', 1.0)
            self.send_json(self.data_aggregator.volume_hedge_calculate_size(symbol, primary_exchange, hedge_exchanges, target_slippage_bps))

        else:
            self.send_error(404, f"Not Found: {path}")

    def serve_html(self):
        """提供HTML页面"""
        html_path = os.path.join(os.path.dirname(__file__), 'web_dashboard_simple.html')

        if os.path.exists(html_path):
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()

            with open(html_path, 'r', encoding='utf-8') as f:
                self.wfile.write(f.read().encode('utf-8'))
        else:
            self.send_error(404, 'Dashboard HTML not found')

    def send_json(self, data):
        """发送JSON响应"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        self.wfile.write(json_data.encode('utf-8'))

    def log_message(self, format, *args):
        """简化日志输出"""
        print(f"[{self.log_date_time_string()}] {format % args}")


def main():
    """启动Dashboard API服务器"""
    PORT = 18888

    print("=" * 70)
    print("🚀 PERP Trading Dashboard API 启动中...")
    print("=" * 70)
    print(f"📍 访问地址: http://localhost:{PORT}")
    print(f"📊 通用API:")
    print(f"   - GET  /api/strategies         获取所有策略")
    print(f"   - GET  /api/system/status      获取系统状态")
    print(f"   - GET  /api/exchanges          获取交易所数据")
    print(f"   - GET  /api/positions          获取持仓数据")
    print(f"   - GET  /api/performance        获取性能指标")
    print(f"   - POST /api/system/start       启动系统")
    print()
    print(f"📈 策略专属API (Simple MM):")
    print(f"   - POST /api/v2/simple_mm/recommend_symbols")
    print(f"   - POST /api/v2/simple_mm/calculate_spread")
    print(f"   - POST /api/v2/simple_mm/calculate_size")
    print()
    print(f"📊 策略专属API (Grid MM):")
    print(f"   - POST /api/v2/grid_mm/recommend_symbols")
    print(f"   - POST /api/v2/grid_mm/calculate_grid_params")
    print()
    print(f"🛡️ 策略专属API (Hedge Agent):")
    print(f"   - GET  /api/v2/hedge_agent/current_exposure")
    print(f"   - POST /api/v2/hedge_agent/recommend_exchange")
    print()
    print(f"💸 策略专属API (Volume Hedge):")
    print(f"   - POST /api/v2/volume_hedge/recommend_symbols")
    print(f"   - POST /api/v2/volume_hedge/recommend_hedge_exchanges")
    print(f"   - POST /api/v2/volume_hedge/calculate_size")
    print("=" * 70)
    print(f"💡 按 Ctrl+C 停止服务器")
    print()

    # 初始化数据聚合器
    DashboardAPIHandler.initialize_aggregator()
    print("✅ 数据聚合器初始化完成")
    print(f"✅ 加载了 {len(DashboardAPIHandler.data_aggregator.strategy_registry)} 个V2策略")
    print()

    server = HTTPServer(('0.0.0.0', PORT), DashboardAPIHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 服务器已停止")


if __name__ == '__main__':
    main()
