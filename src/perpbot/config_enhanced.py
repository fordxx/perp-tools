"""配置管理增强模块

功能:
- 配置验证
- 热重载支持
- 环境变量覆盖
- 配置导出/导入
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ConfigValidationError(Exception):
    """配置验证错误"""
    pass


@dataclass
class ValidationRule:
    """验证规则"""
    field_name: str
    validator: Callable[[Any], bool]
    message: str
    required: bool = True


class ConfigValidator:
    """配置验证器"""

    def __init__(self):
        self.rules: List[ValidationRule] = []

    def add_rule(
        self,
        field_name: str,
        validator: Callable[[Any], bool],
        message: str,
        required: bool = True,
    ):
        """添加验证规则"""
        self.rules.append(ValidationRule(field_name, validator, message, required))

    def validate(self, config: dict) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []

        for rule in self.rules:
            value = config.get(rule.field_name)

            if value is None:
                if rule.required:
                    errors.append(f"必填字段缺失: {rule.field_name}")
                continue

            if not rule.validator(value):
                errors.append(f"{rule.field_name}: {rule.message}")

        return errors


# 常用验证器
def positive_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and v > 0


def non_negative(v: Any) -> bool:
    return isinstance(v, (int, float)) and v >= 0


def percentage(v: Any) -> bool:
    return isinstance(v, (int, float)) and 0 <= v <= 1


def non_empty_string(v: Any) -> bool:
    return isinstance(v, str) and len(v.strip()) > 0


def valid_exchange(v: Any) -> bool:
    valid_exchanges = ["paradex", "extended", "lighter", "edgex", "backpack", "grvt", "aster", "okx"]
    return v in valid_exchanges


def valid_symbol(v: Any) -> bool:
    return isinstance(v, str) and "/" in v


# 默认配置验证器
def create_default_validator() -> ConfigValidator:
    """创建默认配置验证器"""
    validator = ConfigValidator()

    # 交易配置
    validator.add_rule("position_size", positive_number, "必须为正数")
    validator.add_rule("profit_target_pct", percentage, "必须在 0-1 之间", required=False)
    validator.add_rule("max_drawdown_pct", percentage, "必须在 0-1 之间", required=False)
    validator.add_rule("arbitrage_min_profit_pct", percentage, "必须在 0-1 之间", required=False)

    # 交易对
    validator.add_rule("symbols", lambda v: isinstance(v, list) and all(valid_symbol(s) for s in v), "必须为有效的交易对列表", required=False)

    return validator


class ConfigWatcher:
    """配置文件监控器 - 支持热重载"""

    def __init__(
        self,
        config_path: str,
        on_change: Callable[[dict], None],
        check_interval: float = 5.0,
    ):
        self.config_path = Path(config_path)
        self.on_change = on_change
        self.check_interval = check_interval
        self._last_mtime = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """启动监控"""
        if self._running:
            return

        self._running = True
        self._last_mtime = self._get_mtime()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"🔄 配置监控已启动: {self.config_path}")

    def stop(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("配置监控已停止")

    def _get_mtime(self) -> float:
        """获取文件修改时间"""
        try:
            return self.config_path.stat().st_mtime
        except OSError:
            return 0.0

    def _watch_loop(self):
        """监控循环"""
        while self._running:
            try:
                mtime = self._get_mtime()
                if mtime > self._last_mtime:
                    self._last_mtime = mtime
                    logger.info("🔔 检测到配置变更，正在重载...")
                    self._reload()
            except Exception as e:
                logger.error(f"配置监控错误: {e}")

            time.sleep(self.check_interval)

    def _reload(self):
        """重载配置"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            self.on_change(config)
            logger.info("✅ 配置重载成功")
        except Exception as e:
            logger.error(f"配置重载失败: {e}")


class EnhancedConfig:
    """增强配置管理器"""

    def __init__(
        self,
        config_path: Optional[str] = None,
        validator: ConfigValidator = None,
        auto_reload: bool = False,
    ):
        self.config_path = config_path
        self.validator = validator or create_default_validator()
        self._config: Dict[str, Any] = {}
        self._watcher: Optional[ConfigWatcher] = None
        self._change_callbacks: List[Callable[[dict], None]] = []

        load_dotenv()

        if config_path:
            self.load(config_path)

        if auto_reload and config_path:
            self._start_watcher()

    def load(self, path: str) -> dict:
        """加载配置文件"""
        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        # 应用环境变量覆盖
        config = self._apply_env_overrides(config)

        # 验证
        errors = self.validator.validate(config)
        if errors:
            raise ConfigValidationError(f"配置验证失败:\n" + "\n".join(f"  - {e}" for e in errors))

        self._config = config
        self.config_path = path
        logger.info(f"✅ 配置已加载: {path}")

        return config

    def _apply_env_overrides(self, config: dict) -> dict:
        """应用环境变量覆盖"""
        # 支持的环境变量覆盖 (格式: PERPBOT_KEY=value)
        env_mapping = {
            "PERPBOT_POSITION_SIZE": ("position_size", float),
            "PERPBOT_PROFIT_TARGET": ("profit_target_pct", float),
            "PERPBOT_MIN_PROFIT": ("arbitrage_min_profit_pct", float),
            "PERPBOT_MAX_DRAWDOWN": ("max_drawdown_pct", float),
            "PERPBOT_SYMBOLS": ("symbols", lambda v: v.split(",")),
        }

        for env_key, (config_key, converter) in env_mapping.items():
            value = os.getenv(env_key)
            if value:
                try:
                    config[config_key] = converter(value)
                    logger.debug(f"环境变量覆盖: {config_key} = {config[config_key]}")
                except ValueError as e:
                    logger.warning(f"环境变量 {env_key} 值无效: {e}")

        return config

    def _start_watcher(self):
        """启动配置监控"""
        if not self.config_path:
            return

        self._watcher = ConfigWatcher(
            self.config_path,
            self._on_config_change,
        )
        self._watcher.start()

    def _on_config_change(self, new_config: dict):
        """配置变更回调"""
        try:
            new_config = self._apply_env_overrides(new_config)
            errors = self.validator.validate(new_config)
            if errors:
                logger.error("配置验证失败，保持原配置:\n" + "\n".join(f"  - {e}" for e in errors))
                return

            old_config = self._config.copy()
            self._config = new_config

            # 触发回调
            for callback in self._change_callbacks:
                try:
                    callback(new_config)
                except Exception as e:
                    logger.error(f"配置变更回调失败: {e}")

            logger.info("✅ 配置已热重载")
        except Exception as e:
            logger.error(f"配置热重载失败: {e}")

    def on_change(self, callback: Callable[[dict], None]):
        """注册配置变更回调"""
        self._change_callbacks.append(callback)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value

    def save(self, path: str = None):
        """保存配置到文件"""
        path = path or self.config_path
        if not path:
            raise ValueError("未指定配置文件路径")

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)

        logger.info(f"✅ 配置已保存: {path}")

    def export_env(self) -> str:
        """导出为环境变量格式"""
        lines = ["# PerpBot 配置导出"]
        for key, value in self._config.items():
            if isinstance(value, (str, int, float, bool)):
                env_key = f"PERPBOT_{key.upper()}"
                lines.append(f"{env_key}={value}")
            elif isinstance(value, list):
                env_key = f"PERPBOT_{key.upper()}"
                lines.append(f"{env_key}={','.join(str(v) for v in value)}")
        return "\n".join(lines)

    @property
    def config(self) -> dict:
        """获取完整配置"""
        return self._config.copy()

    def stop(self):
        """停止配置管理器"""
        if self._watcher:
            self._watcher.stop()


# 全局配置实例
_global_config: Optional[EnhancedConfig] = None


def get_config() -> EnhancedConfig:
    """获取全局配置实例"""
    global _global_config
    if _global_config is None:
        _global_config = EnhancedConfig()
    return _global_config


def load_config(path: str, auto_reload: bool = False) -> EnhancedConfig:
    """加载配置"""
    global _global_config
    _global_config = EnhancedConfig(path, auto_reload=auto_reload)
    return _global_config
