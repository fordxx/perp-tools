from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


# Load `.env` from current working directory (if present) so running `uvicorn ...`
# does not require exporting environment variables manually.
load_dotenv()


def _getenv(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _getenv_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None and value != "" else default


def _getenv_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None and value != "" else default


def _getenv_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _getenv_list(name: str, default: str) -> list[str]:
    value = os.getenv(name)
    raw = value if value is not None and value != "" else default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _getenv_optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value


def _getenv_csv_set(name: str, default: str = "") -> set[str]:
    return {item.strip().lower() for item in _getenv_list(name, default) if item.strip()}


def _validate_settings(settings: "Settings") -> None:
    """Validate settings for common configuration errors."""
    import sys

    errors = []
    warnings = []

    if settings.tv_webhook_secret == "CHANGE_ME":
        if settings.trading_enabled:
            errors.append("TV_WEBHOOK_SECRET is default (CHANGE_ME); set a real secret before trading")
        else:
            warnings.append("TV_WEBHOOK_SECRET is default (CHANGE_ME); set a real secret before trading")

    # Validate TP percentages
    total_tp_pct = settings.tp1_pct + settings.tp2_pct + settings.tp3_pct + settings.tp4_pct
    if abs(total_tp_pct - 1.0) > 0.01:
        warnings.append(
            f"TP percentages sum to {total_tp_pct:.2%} (expected 100%). "
            f"TP1={settings.tp1_pct:.1%} TP2={settings.tp2_pct:.1%} "
            f"TP3={settings.tp3_pct:.1%} TP4={settings.tp4_pct:.1%}"
        )

    # Validate R-multiples are ascending
    if not (settings.tp1_r < settings.tp2_r < settings.tp3_r < settings.tp4_r):
        warnings.append(
            f"TP R-multiples should be ascending: "
            f"TP1={settings.tp1_r} TP2={settings.tp2_r} TP3={settings.tp3_r} TP4={settings.tp4_r}"
        )

    # Validate trailing stop
    if settings.trail_start_r <= settings.trail_back_r:
        warnings.append(
            f"TRAIL_START_R ({settings.trail_start_r}) should be > TRAIL_BACK_R ({settings.trail_back_r})"
        )

    # Validate risk-based sizing vs fixed sizing
    if settings.trading_enabled and settings.risk_per_trade_usdt == 0:
        warnings.append(
            f"Trading enabled with RISK_PER_TRADE_USDT=0, using fixed ORDER_SZ={settings.order_sz}. "
            "This may create inconsistent risk across different symbols!"
        )

    # Validate ladder orders
    if settings.ladder_enabled:
        total_ladder_pct = settings.ladder_market_pct + settings.ladder_level1_pct + settings.ladder_level2_pct + settings.ladder_level3_pct
        if abs(total_ladder_pct - 1.0) > 0.01:
            warnings.append(
                f"Ladder order percentages sum to {total_ladder_pct:.2%} (expected 100%). "
                f"Market={settings.ladder_market_pct:.1%} L1={settings.ladder_level1_pct:.1%} "
                f"L2={settings.ladder_level2_pct:.1%} L3={settings.ladder_level3_pct:.1%}"
            )
        if not (settings.ladder_level1_bps < settings.ladder_level2_bps < settings.ladder_level3_bps):
            warnings.append(
                f"Ladder levels should be ascending: "
                f"Level1={settings.ladder_level1_bps}bps Level2={settings.ladder_level2_bps}bps "
                f"Level3={settings.ladder_level3_bps}bps"
            )

    # Validate exchange credentials
    if settings.trading_enabled:
        if settings.exchange == "okx":
            if not all([settings.okx_api_key, settings.okx_api_secret, settings.okx_api_passphrase]):
                errors.append("OKX credentials incomplete (API_KEY, API_SECRET, API_PASSPHRASE required)")
        if settings.exchange == "paradex":
            if not all([os.getenv("PARADEX_L2_PRIVATE_KEY"), os.getenv("PARADEX_ACCOUNT_ADDRESS")]):
                errors.append("Paradex credentials incomplete (PARADEX_L2_PRIVATE_KEY, PARADEX_ACCOUNT_ADDRESS required)")
        # Extended validation would need env vars check

    # Print warnings
    for warning in warnings:
        print(f"⚠️  CONFIG WARNING: {warning}", file=sys.stderr)

    # Print errors and exit if critical
    for error in errors:
        print(f"❌ CONFIG ERROR: {error}", file=sys.stderr)

    if errors:
        sys.exit(1)


@dataclass(frozen=True)
class Settings:
    tv_webhook_secret: str = _getenv("TV_WEBHOOK_SECRET", "CHANGE_ME")

    okx_base_url: str = _getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/")
    okx_api_key: str = _getenv("OKX_API_KEY", "")
    okx_api_secret: str = _getenv("OKX_API_SECRET", "")
    okx_api_passphrase: str = _getenv("OKX_API_PASSPHRASE", "")
    okx_td_mode: str = _getenv("OKX_TD_MODE", "cross")
    exchange: str = _getenv("EXCHANGE", "okx").lower()  # okx | extended | paradex
    trading_enabled: bool = _getenv_bool("TRADING_ENABLED", False)
    paper_trade_tfs: set[str] = frozenset(_getenv_csv_set("PAPER_TRADE_TFS", ""))

    symbol_allowlist: set[str] = frozenset(
        s.strip()
        for s in _getenv("SYMBOL_ALLOWLIST", "ETH-USDT-SWAP").split(",")
        if s.strip()
    )

    zone_ttl_seconds: int = _getenv_int("ZONE_TTL_SECONDS", 900)
    cooldown_seconds: int = _getenv_int("COOLDOWN_SECONDS", 120)
    dedupe_ttl_seconds: int = _getenv_int("DEDUPE_TTL_SECONDS", 1800)
    health_log_seconds: int = _getenv_int("HEALTH_LOG_SECONDS", 60)

    enable_long: bool = _getenv_bool("ENABLE_LONG", True)
    enable_short: bool = _getenv_bool("ENABLE_SHORT", True)

    order_type: str = _getenv("ORDER_TYPE", "market").lower()
    limit_slippage_bps: float = _getenv_float("LIMIT_SLIPPAGE_BPS", 5.0)
    order_sz: str = _getenv("ORDER_SZ", "1")
    risk_per_trade_usdt: float = _getenv_float("RISK_PER_TRADE_USDT", 0.0)
    risk_per_trade_by_tf: str = _getenv("RISK_PER_TRADE_BY_TF", "15m:100,30m:300,1h:300,4h:300")  # Risk in USDT by timeframe

    # Ladder orders (70% market + 30% limit in 2 levels)
    ladder_enabled: bool = _getenv_bool("LADDER_ENABLED", False)
    ladder_market_pct: float = _getenv_float("LADDER_MARKET_PCT", 0.70)   # 70% market order
    ladder_level1_bps: float = _getenv_float("LADDER_LEVEL1_BPS", 3.0)    # L1: -3bps from signal
    ladder_level1_pct: float = _getenv_float("LADDER_LEVEL1_PCT", 0.20)   # L1: 20% of position
    ladder_level2_bps: float = _getenv_float("LADDER_LEVEL2_BPS", 8.0)    # L2: -8bps from signal
    ladder_level2_pct: float = _getenv_float("LADDER_LEVEL2_PCT", 0.10)   # L2: 10% of position
    ladder_level3_bps: float = _getenv_float("LADDER_LEVEL3_BPS", 15.0)   # Not used
    ladder_level3_pct: float = _getenv_float("LADDER_LEVEL3_PCT", 0.0)    # Not used

    # Two-limit entry mode (pure limit orders, prices derived from stop-loss distance)
    entry_two_limit_enabled: bool = _getenv_bool("ENTRY_TWO_LIMIT_ENABLED", False)
    entry_two_limit_l1_r: float = _getenv_float("ENTRY_TWO_LIMIT_L1_R", 0.25)
    entry_two_limit_l2_r: float = _getenv_float("ENTRY_TWO_LIMIT_L2_R", 0.65)
    entry_two_limit_l1_pct: float = _getenv_float("ENTRY_TWO_LIMIT_L1_PCT", 0.70)
    entry_two_limit_l2_pct: float = _getenv_float("ENTRY_TWO_LIMIT_L2_PCT", 0.30)
    entry_two_limit_ref_bar: str = _getenv("ENTRY_TWO_LIMIT_REF_BAR", "1m").lower()
    entry_two_limit_timeout_candles: float = _getenv_float("ENTRY_TWO_LIMIT_TIMEOUT_CANDLES", 1.0)
    entry_two_limit_timeout_candles_by_tf: str = _getenv("ENTRY_TWO_LIMIT_TIMEOUT_CANDLES_BY_TF", "")
    entry_two_limit_poll_seconds: float = _getenv_float("ENTRY_TWO_LIMIT_POLL_SECONDS", 2.0)

    # Wait time configuration (by timeframe) - Shorter wait since 70% market fills immediately
    # 基础等待时间（无成交时的等待）
    ladder_wait_candles_by_tf: str = _getenv("LADDER_WAIT_CANDLES_BY_TF", "1m:0.5,3m:0.5,5m:0.5,15m:0.3,30m:0.3,1h:0.2,4h:0.2")
    # 最大等待时间（有部分成交时的延长等待）
    ladder_max_wait_candles_by_tf: str = _getenv("LADDER_MAX_WAIT_CANDLES_BY_TF", "1m:1,3m:1,5m:1,15m:0.8,30m:0.8,1h:0.5,4h:0.5")
    # 价格远离阈值（可以稍微放宽）
    ladder_price_distance_by_tf: str = _getenv("LADDER_PRICE_DISTANCE_BY_TF", "1m:0.5,3m:0.5,5m:0.5,15m:0.6,30m:0.7,1h:0.8,4h:1.0")

    # Default values (if timeframe not configured)
    ladder_wait_candles: float = _getenv_float("LADDER_WAIT_CANDLES", 0.5)
    ladder_max_wait_candles: float = _getenv_float("LADDER_MAX_WAIT_CANDLES", 1.0)
    ladder_price_distance_pct: float = _getenv_float("LADDER_PRICE_DISTANCE_PCT", 0.5)

    # TODO: Add global risk controls
    # max_total_exposure_usdt: float = 0.0  # Maximum total position value
    # max_positions: int = 0  # Maximum number of concurrent positions
    # max_position_per_symbol_usdt: float = 0.0  # Per-symbol position limit

    pivot_len: int = _getenv_int("PIVOT_LEN", 3)
    atr_len: int = _getenv_int("ATR_LEN", 14)
    atr_buffer_mult: float = _getenv_float("ATR_BUFFER_MULT", 0.2)
    min_buffer_bps: float = _getenv_float("MIN_BUFFER_BPS", 3.0)
    min_stop_distance_bps: float = _getenv_float("MIN_STOP_DISTANCE_BPS", 0.0)
    stop_method: str = _getenv("STOP_METHOD", "lookback").lower()  # lookback | pivot
    stop_lookback_bars: int = _getenv_int("STOP_LOOKBACK_BARS", 50)
    stop_lookback_by_tf: str = _getenv("STOP_LOOKBACK_BY_TF", "")  # e.g., "5m:25,15m:30,1h:40"
    backup_sl_enabled: bool = _getenv_bool("BACKUP_SL_ENABLED", False)  # Try limit order SL as backup

    # Optional pattern filters (approximate, pivot-based)
    pattern_long: str = _getenv("PATTERN_LONG", "none").lower()  # none | w_bottom
    pattern_short: str = _getenv("PATTERN_SHORT", "none").lower()  # none | hs_top
    pattern_pivot_len: int = _getenv_int("PATTERN_PIVOT_LEN", 3)
    pattern_tol_pct: float = _getenv_float("PATTERN_TOL_PCT", 0.004)
    w_min_bounce_pct: float = _getenv_float("W_MIN_BOUNCE_PCT", 0.003)
    w_require_breakout: bool = _getenv_bool("W_REQUIRE_BREAKOUT", False)
    hs_min_shoulder_drop_pct: float = _getenv_float("HS_MIN_SHOULDER_DROP_PCT", 0.003)
    hs_require_breakdown: bool = _getenv_bool("HS_REQUIRE_BREAKDOWN", False)

    # Take-profit ladder (R-multiples of stop distance)
    tp_enabled: bool = _getenv_bool("TP_ENABLED", True)
    tp1_r: float = _getenv_float("TP1_R", 1.5)
    tp1_pct: float = _getenv_float("TP1_PCT", 0.70)
    tp2_r: float = _getenv_float("TP2_R", 2.0)
    tp2_pct: float = _getenv_float("TP2_PCT", 0.15)
    tp3_r: float = _getenv_float("TP3_R", 2.5)
    tp3_pct: float = _getenv_float("TP3_PCT", 0.10)
    tp4_r: float = _getenv_float("TP4_R", 3.5)
    tp4_pct: float = _getenv_float("TP4_PCT", 0.05)
    trail_start_r: float = _getenv_float("TRAIL_START_R", 0.8)
    trail_back_r: float = _getenv_float("TRAIL_BACK_R", 0.75)
    manager_poll_seconds: float = _getenv_float("MANAGER_POLL_SECONDS", 2.0)

    # RSI ML filter (matches TradingView defaults)
    rsi_length: int = _getenv_int("RSI_LENGTH", 14)
    rsi_filter_enabled: bool = _getenv_bool("RSI_FILTER_ENABLED", False)
    rsi_debug: bool = _getenv_bool("RSI_DEBUG", False)
    rsi_use_live_candle: bool = _getenv_bool("RSI_USE_LIVE_CANDLE", True)
    rsi_threshold_mode: str = _getenv("RSI_THRESHOLD_MODE", "kmeans").lower()
    rsi_smooth: bool = _getenv_bool("RSI_SMOOTH", True)
    rsi_smooth_period: int = _getenv_int("RSI_SMOOTH_PERIOD", 4)
    rsi_ma_type: str = _getenv("RSI_MA_TYPE", "ema")
    rsi_pct_low: float = _getenv_float("RSI_PCT_LOW", 25.0)
    rsi_pct_high: float = _getenv_float("RSI_PCT_HIGH", 75.0)
    rsi_pct_by_tf: str = _getenv("RSI_PCT_BY_TF", "")
    rsi_pct_by_symbol: str = _getenv("RSI_PCT_BY_SYMBOL", "")
    rsi_max_data: int = _getenv_int("RSI_MAX_DATA", 3000)
    rsi_max_data_by_tf: str = _getenv("RSI_MAX_DATA_BY_TF", "")
    rsi_max_data_by_symbol: str = _getenv("RSI_MAX_DATA_BY_SYMBOL", "")
    rsi_max_iter: int = _getenv_int("RSI_MAX_ITER", 1000)
    rsi_allow_no_zone: bool = _getenv_bool("RSI_ALLOW_NO_ZONE", True)

    candle_ws_enabled: bool = _getenv_bool("CANDLE_WS_ENABLED", True)
    candle_ws_okx_enabled: bool = _getenv_bool("CANDLE_WS_OKX_ENABLED", True)
    candle_ws_extended_enabled: bool = _getenv_bool("CANDLE_WS_EXTENDED_ENABLED", True)
    candle_ws_tfs: tuple[str, ...] = tuple(_getenv_list("CANDLE_WS_TFS", "1h"))
    candle_cache_ttl_seconds: int = _getenv_int("CANDLE_CACHE_TTL_SECONDS", 30)
    candle_cache_max_bars: int = _getenv_int("CANDLE_CACHE_MAX_BARS", 4000)
    candle_ws_okx_max_subs: int = _getenv_int("CANDLE_WS_OKX_MAX_SUBS", 200)
    candle_ws_extended_max_subs: int = _getenv_int("CANDLE_WS_EXTENDED_MAX_SUBS", 50)
    candle_ws_extended_idle_seconds: int = _getenv_int("CANDLE_WS_EXTENDED_IDLE_SECONDS", 600)
    candle_ws_symbol_tfs: str = _getenv("CANDLE_WS_SYMBOL_TFS", "")
    candle_ws_symbol_tfs_file: str | None = _getenv_optional("CANDLE_WS_SYMBOL_TFS_FILE")
    candle_ws_symbol_tfs_strict: bool = _getenv_bool("CANDLE_WS_SYMBOL_TFS_STRICT", False)
    extended_refresh_seconds: int = _getenv_int("EXTENDED_REFRESH_SECONDS", 300)
    extended_refresh_enabled: bool = _getenv_bool("EXTENDED_REFRESH_ENABLED", True)
    extended_refresh_sl_enabled: bool = _getenv_bool("EXTENDED_REFRESH_SL_ENABLED", True)
    extended_refresh_tp_enabled: bool = _getenv_bool("EXTENDED_REFRESH_TP_ENABLED", True)

    # Lighter protection refresh
    lighter_refresh_seconds: int = _getenv_int("LIGHTER_REFRESH_SECONDS", 60)
    lighter_refresh_enabled: bool = _getenv_bool("LIGHTER_REFRESH_ENABLED", True)
    lighter_refresh_sl_enabled: bool = _getenv_bool("LIGHTER_REFRESH_SL_ENABLED", True)
    lighter_refresh_tp_enabled: bool = _getenv_bool("LIGHTER_REFRESH_TP_ENABLED", True)
    lighter_entry_ttl_seconds: int = _getenv_int("LIGHTER_ENTRY_TTL_SECONDS", 21600)
    lighter_block_duplicate_positions: bool = _getenv_bool("LIGHTER_BLOCK_DUPLICATE_POSITIONS", False)


SETTINGS = Settings()
_validate_settings(SETTINGS)


# Parse STOP_LOOKBACK_BY_TF into a dictionary for quick lookup
def _parse_lookback_by_tf(config_str: str) -> dict[str, int]:
    """Parse STOP_LOOKBACK_BY_TF config string into a dict.

    Example: "5m:25,15m:30,1h:40" -> {"5m": 25, "15m": 30, "1h": 40}
    """
    result = {}
    if not config_str:
        return result

    for pair in config_str.split(","):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(":")
        if len(parts) == 2:
            tf = parts[0].strip()
            try:
                bars = int(parts[1].strip())
                result[tf] = bars
            except ValueError:
                pass  # Invalid format, skip
    return result


LOOKBACK_BY_TF = _parse_lookback_by_tf(SETTINGS.stop_lookback_by_tf)


def get_lookback_bars(tf: str) -> int:
    """Get LOOKBACK_BARS for a specific timeframe, fallback to default."""
    return LOOKBACK_BY_TF.get(tf, SETTINGS.stop_lookback_bars)


# Parse ladder wait candles by timeframe
def _parse_float_by_tf(config_str: str) -> dict[str, float]:
    """Parse config string like '1m:3,5m:2,1h:1' into dict."""
    result = {}
    if not config_str:
        return result
    for pair in config_str.split(","):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(":")
        if len(parts) == 2:
            tf = parts[0].strip()
            try:
                value = float(parts[1].strip())
                result[tf] = value
            except ValueError:
                pass
    return result


LADDER_WAIT_CANDLES_BY_TF = _parse_float_by_tf(SETTINGS.ladder_wait_candles_by_tf)
LADDER_MAX_WAIT_CANDLES_BY_TF = _parse_float_by_tf(SETTINGS.ladder_max_wait_candles_by_tf)
LADDER_PRICE_DISTANCE_BY_TF = _parse_float_by_tf(SETTINGS.ladder_price_distance_by_tf)
ENTRY_TWO_LIMIT_TIMEOUT_CANDLES_BY_TF = _parse_float_by_tf(SETTINGS.entry_two_limit_timeout_candles_by_tf)


def get_ladder_wait_candles(tf: str) -> float:
    """Get base wait candles for a specific timeframe."""
    return LADDER_WAIT_CANDLES_BY_TF.get(tf, SETTINGS.ladder_wait_candles)


def get_ladder_max_wait_candles(tf: str) -> float:
    """Get max wait candles for a specific timeframe."""
    return LADDER_MAX_WAIT_CANDLES_BY_TF.get(tf, SETTINGS.ladder_max_wait_candles)


def get_ladder_price_distance(tf: str) -> float:
    """Get price distance threshold (%) for a specific timeframe."""
    return LADDER_PRICE_DISTANCE_BY_TF.get(tf, SETTINGS.ladder_price_distance_pct)


def get_entry_two_limit_timeout_candles(tf: str) -> float:
    """Get two-limit entry timeout candles for a specific timeframe."""
    return ENTRY_TWO_LIMIT_TIMEOUT_CANDLES_BY_TF.get(tf, SETTINGS.entry_two_limit_timeout_candles)


def tf_to_seconds(tf: str) -> int:
    """Convert timeframe string to seconds.

    Examples:
        1m  -> 60
        3m  -> 180
        5m  -> 300
        15m -> 900
        30m -> 1800
        1h  -> 3600
        4h  -> 14400
        1d  -> 86400
    """
    tf = tf.lower().strip()

    # Extract number and unit
    import re
    match = re.match(r'^(\d+)([mhd])$', tf)
    if not match:
        # Unknown format, default to 5m
        return 300

    num = int(match.group(1))
    unit = match.group(2)

    if unit == 'm':
        return num * 60
    elif unit == 'h':
        return num * 3600
    elif unit == 'd':
        return num * 86400
    else:
        return 300  # default 5m


# Parse RISK_PER_TRADE_BY_TF into a dictionary for quick lookup
RISK_BY_TF = _parse_float_by_tf(SETTINGS.risk_per_trade_by_tf)


def get_risk_per_trade(tf: str) -> float:
    """Get risk amount (USDT) for a specific timeframe, fallback to default."""
    return RISK_BY_TF.get(tf, SETTINGS.risk_per_trade_usdt)
