from __future__ import annotations

from dataclasses import dataclass
import os

import yaml


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


@dataclass(frozen=True)
class TradingViewSettings:
    enabled: bool
    secret: str
    symbol_allowlist: set[str]
    allow_all_symbols: bool
    exchange_allowlist: set[str]
    default_exchange: str
    exchange_aliases: dict[str, str]
    symbol_aliases: dict[str, str]
    symbol_overrides_by_exchange: dict[str, dict[str, str]]
    zone_ttl_seconds: int
    cooldown_seconds: int
    enable_long: bool
    enable_short: bool
    order_size: float
    order_size_by_exchange: dict[str, float]
    order_size_by_symbol: dict[str, float]
    candles_base_url: str
    candle_limit: int
    pivot_len: int
    atr_len: int
    atr_buffer_mult: float
    min_buffer_bps: float
    stop_method: str
    stop_lookback_bars: int
    tp_rr: float

    @staticmethod
    def from_env() -> "TradingViewSettings":
        cfg_path = os.getenv("PERPBOT_TV_CONFIG_PATH") or os.getenv("TV_CONFIG_PATH") or ""
        cfg: dict = {}
        if cfg_path:
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            except FileNotFoundError:
                cfg = {}

        # Allow legacy tw168 env names as fallback.
        secret = (
            os.getenv("PERPBOT_TV_WEBHOOK_SECRET")
            or os.getenv("TV_WEBHOOK_SECRET")
            or cfg.get("secret")
            or "CHANGE_ME"
        )

        ex_allow = (
            os.getenv("PERPBOT_TV_EXCHANGE_ALLOWLIST")
            or os.getenv("TV_EXCHANGE_ALLOWLIST")
            or ",".join(cfg.get("exchange_allowlist") or [])
            or ""
        )
        exchange_allowlist = {s.strip().lower() for s in ex_allow.split(",") if s.strip()}

        default_exchange = (
            os.getenv("PERPBOT_TV_DEFAULT_EXCHANGE")
            or os.getenv("TV_EXCHANGE")
            or cfg.get("default_exchange")
            or "okx"
        ).lower()
        if exchange_allowlist and default_exchange not in exchange_allowlist:
            exchange_allowlist.add(default_exchange)

        allow = (
            os.getenv("PERPBOT_TV_SYMBOL_ALLOWLIST")
            or os.getenv("SYMBOL_ALLOWLIST")
            or ",".join(cfg.get("symbol_allowlist") or [])
            or "ETH-USDT-SWAP"
        )
        allowlist = {s.strip() for s in allow.split(",") if s.strip()}
        allow_all = _getenv_bool("PERPBOT_TV_ALLOW_ALL_SYMBOLS", False) or ("*" in {a.strip() for a in allowlist})

        def _norm_map(value: object) -> dict[str, str]:
            if not isinstance(value, dict):
                return {}
            out: dict[str, str] = {}
            for k, v in value.items():
                if k is None or v is None:
                    continue
                out[str(k).strip().lower()] = str(v).strip()
            return out

        def _norm_symbol_map(value: object) -> dict[str, str]:
            if not isinstance(value, dict):
                return {}
            out: dict[str, str] = {}
            for k, v in value.items():
                if k is None or v is None:
                    continue
                out[str(k).strip().upper()] = str(v).strip()
            return out

        exchange_aliases = _norm_map(cfg.get("exchange_aliases"))
        symbol_aliases = _norm_symbol_map(cfg.get("symbol_aliases"))

        symbol_overrides_by_exchange: dict[str, dict[str, str]] = {}
        raw_overrides = cfg.get("symbol_overrides_by_exchange") or {}
        if isinstance(raw_overrides, dict):
            for ex, mapping in raw_overrides.items():
                if not isinstance(mapping, dict):
                    continue
                ex_key = str(ex).strip().lower()
                symbol_overrides_by_exchange[ex_key] = _norm_symbol_map(mapping)

        order_size = float(
            os.getenv("PERPBOT_TV_ORDER_SIZE")
            or os.getenv("ORDER_SZ")
            or cfg.get("order_size")
            or "1"
        )
        order_size_by_exchange_raw = cfg.get("order_size_by_exchange") or {}
        order_size_by_exchange: dict[str, float] = {}
        if isinstance(order_size_by_exchange_raw, dict):
            for k, v in order_size_by_exchange_raw.items():
                try:
                    order_size_by_exchange[str(k).strip().lower()] = float(v)
                except Exception:
                    continue

        order_size_by_symbol_raw = cfg.get("order_size_by_symbol") or {}
        order_size_by_symbol: dict[str, float] = {}
        if isinstance(order_size_by_symbol_raw, dict):
            for k, v in order_size_by_symbol_raw.items():
                try:
                    order_size_by_symbol[str(k).strip().upper()] = float(v)
                except Exception:
                    continue

        # Also parse from environment variable JSON if exists
        sz_by_sym_env = os.getenv("PERPBOT_TV_ORDER_SIZE_BY_SYMBOL")
        if sz_by_sym_env:
            try:
                import json
                env_map = json.loads(sz_by_sym_env)
                if isinstance(env_map, dict):
                    for k, v in env_map.items():
                        order_size_by_symbol[str(k).strip().upper()] = float(v)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to parse PERPBOT_TV_ORDER_SIZE_BY_SYMBOL: %s", e)

        return TradingViewSettings(
            enabled=_getenv_bool("PERPBOT_TV_ENABLED", bool(cfg.get("enabled", True))),
            secret=secret,
            symbol_allowlist=allowlist,
            allow_all_symbols=allow_all,
            exchange_allowlist=exchange_allowlist,
            default_exchange=default_exchange,
            exchange_aliases=exchange_aliases,
            symbol_aliases=symbol_aliases,
            symbol_overrides_by_exchange=symbol_overrides_by_exchange,
            zone_ttl_seconds=_getenv_int("PERPBOT_TV_ZONE_TTL_SECONDS", _getenv_int("ZONE_TTL_SECONDS", 900)),
            cooldown_seconds=_getenv_int("PERPBOT_TV_COOLDOWN_SECONDS", _getenv_int("COOLDOWN_SECONDS", 120)),
            enable_long=_getenv_bool("PERPBOT_TV_ENABLE_LONG", _getenv_bool("ENABLE_LONG", True)),
            enable_short=_getenv_bool("PERPBOT_TV_ENABLE_SHORT", _getenv_bool("ENABLE_SHORT", True)),
            order_size=order_size,
            order_size_by_exchange=order_size_by_exchange,
            order_size_by_symbol=order_size_by_symbol,
            candles_base_url=_getenv("PERPBOT_TV_CANDLES_BASE_URL", os.getenv("OKX_BASE_URL", "https://www.okx.com")).rstrip("/"),
            candle_limit=_getenv_int("PERPBOT_TV_CANDLE_LIMIT", 300),
            pivot_len=_getenv_int("PERPBOT_TV_PIVOT_LEN", _getenv_int("PIVOT_LEN", 3)),
            atr_len=_getenv_int("PERPBOT_TV_ATR_LEN", _getenv_int("ATR_LEN", 14)),
            atr_buffer_mult=_getenv_float("PERPBOT_TV_ATR_BUFFER_MULT", _getenv_float("ATR_BUFFER_MULT", 0.2)),
            min_buffer_bps=_getenv_float("PERPBOT_TV_MIN_BUFFER_BPS", _getenv_float("MIN_BUFFER_BPS", 3.0)),
            stop_method=_getenv("PERPBOT_TV_STOP_METHOD", os.getenv("STOP_METHOD", "lookback")).lower(),
            stop_lookback_bars=_getenv_int("PERPBOT_TV_STOP_LOOKBACK_BARS", _getenv_int("STOP_LOOKBACK_BARS", 50)),
            tp_rr=_getenv_float("PERPBOT_TV_TP_RR", _getenv_float("TP3_R", 3.0)),
        )
