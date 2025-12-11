"""增强通知系统

支持多种通知渠道：
- Telegram
- Discord
- 微信 (WxPusher)
- 飞书 (Lark)
- 自定义 Webhook
- 声音告警
- 邮件通知 (SMTP)
"""
from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.text import MIMEText
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """统一通知配置"""
    # Telegram
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    
    # Discord
    discord_webhook_url: Optional[str] = None
    
    # 微信 WxPusher
    wxpusher_app_token: Optional[str] = None
    wxpusher_uid: Optional[str] = None
    
    # 飞书 Lark
    lark_webhook: Optional[str] = None
    
    # 自定义 Webhook
    custom_webhook_url: Optional[str] = None
    
    # 邮件
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    email_to: Optional[str] = None
    
    # 控制台和声音
    console: bool = True
    play_sound: bool = False
    
    # 启用的渠道
    enabled_channels: List[str] = field(default_factory=lambda: ["console"])

    @classmethod
    def from_env(cls) -> "NotificationConfig":
        """从环境变量加载配置"""
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            wxpusher_app_token=os.getenv("WXPUSHER_APP_TOKEN"),
            wxpusher_uid=os.getenv("WXPUSHER_UID"),
            lark_webhook=os.getenv("LARK_WEBHOOK"),
            custom_webhook_url=os.getenv("WEBHOOK_URL"),
            smtp_host=os.getenv("SMTP_HOST"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
            email_to=os.getenv("EMAIL_TO"),
            console=os.getenv("NOTIFY_CONSOLE", "true").lower() == "true",
            play_sound=os.getenv("NOTIFY_SOUND", "false").lower() == "true",
        )


class NotificationService:
    """统一通知服务"""

    def __init__(self, config: NotificationConfig = None):
        self.config = config or NotificationConfig.from_env()
        self._client = httpx.Client(timeout=10.0)

    def send(
        self,
        message: str,
        title: str = "PerpBot 通知",
        channels: List[str] = None,
        level: str = "info",
    ) -> dict:
        """
        发送通知到指定渠道
        
        Args:
            message: 通知内容
            title: 通知标题
            channels: 要发送的渠道列表，None 表示使用配置的默认渠道
            level: 通知级别 (info, warning, error, success)
            
        Returns:
            发送结果统计
        """
        channels = channels or self.config.enabled_channels or ["console"]
        results = {"sent": 0, "failed": 0, "skipped": 0}

        # 添加时间戳和级别标记
        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}.get(level, "📢")
        formatted_message = f"{emoji} [{datetime.now().strftime('%H:%M:%S')}] {message}"

        for channel in channels:
            try:
                if channel == "console" and self.config.console:
                    self._send_console(formatted_message)
                    results["sent"] += 1
                elif channel == "sound" and self.config.play_sound:
                    self._send_sound()
                    results["sent"] += 1
                elif channel == "telegram":
                    if self._send_telegram(formatted_message):
                        results["sent"] += 1
                    else:
                        results["skipped"] += 1
                elif channel == "discord":
                    if self._send_discord(title, message, level):
                        results["sent"] += 1
                    else:
                        results["skipped"] += 1
                elif channel == "wxpusher":
                    if self._send_wxpusher(title, message):
                        results["sent"] += 1
                    else:
                        results["skipped"] += 1
                elif channel == "lark":
                    if self._send_lark(title, message):
                        results["sent"] += 1
                    else:
                        results["skipped"] += 1
                elif channel == "webhook":
                    if self._send_webhook(title, message, level):
                        results["sent"] += 1
                    else:
                        results["skipped"] += 1
                elif channel == "email":
                    if self._send_email(title, message):
                        results["sent"] += 1
                    else:
                        results["skipped"] += 1
                else:
                    results["skipped"] += 1
            except Exception as e:
                logger.error(f"发送 {channel} 通知失败: {e}")
                results["failed"] += 1

        return results

    def _send_console(self, message: str):
        """控制台输出"""
        logger.info(message)

    def _send_sound(self):
        """声音告警"""
        print("\a", end="", flush=True)

    def _send_telegram(self, message: str) -> bool:
        """发送 Telegram 消息"""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        resp = self._client.post(url, json={
            "chat_id": self.config.telegram_chat_id,
            "text": message,
            "parse_mode": "HTML",
        })
        return resp.status_code == 200

    def _send_discord(self, title: str, message: str, level: str) -> bool:
        """发送 Discord 消息"""
        if not self.config.discord_webhook_url:
            return False

        # Discord Embed 颜色
        colors = {
            "info": 3447003,      # 蓝色
            "warning": 16776960,  # 黄色
            "error": 15158332,    # 红色
            "success": 3066993,   # 绿色
        }

        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": colors.get(level, 3447003),
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "PerpBot"},
            }]
        }

        resp = self._client.post(self.config.discord_webhook_url, json=payload)
        return resp.status_code in (200, 204)

    def _send_wxpusher(self, title: str, message: str) -> bool:
        """发送微信消息 (WxPusher)"""
        if not self.config.wxpusher_app_token or not self.config.wxpusher_uid:
            return False

        url = "https://wxpusher.zjiecode.com/api/send/message"
        payload = {
            "appToken": self.config.wxpusher_app_token,
            "content": f"<h3>{title}</h3><p>{message}</p>",
            "contentType": 2,  # HTML
            "uids": [self.config.wxpusher_uid],
        }

        resp = self._client.post(url, json=payload)
        return resp.status_code == 200

    def _send_lark(self, title: str, message: str) -> bool:
        """发送飞书消息"""
        if not self.config.lark_webhook:
            return False

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": [{
                    "tag": "div",
                    "text": {"tag": "plain_text", "content": message},
                }],
            },
        }

        resp = self._client.post(self.config.lark_webhook, json=payload)
        return resp.status_code == 200

    def _send_webhook(self, title: str, message: str, level: str) -> bool:
        """发送通用 Webhook"""
        if not self.config.custom_webhook_url:
            return False

        payload = {
            "title": title,
            "message": message,
            "level": level,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "perpbot",
        }

        resp = self._client.post(self.config.custom_webhook_url, json=payload)
        return resp.status_code == 200

    def _send_email(self, title: str, message: str) -> bool:
        """发送邮件"""
        if not all([
            self.config.smtp_host,
            self.config.smtp_user,
            self.config.smtp_password,
            self.config.email_to,
        ]):
            return False

        try:
            msg = MIMEText(message, "html")
            msg["Subject"] = title
            msg["From"] = self.config.smtp_user
            msg["To"] = self.config.email_to

            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False

    # 便捷方法
    def info(self, message: str, title: str = "PerpBot", channels: List[str] = None):
        """发送信息通知"""
        return self.send(message, title, channels, level="info")

    def warning(self, message: str, title: str = "PerpBot 警告", channels: List[str] = None):
        """发送警告通知"""
        return self.send(message, title, channels, level="warning")

    def error(self, message: str, title: str = "PerpBot 错误", channels: List[str] = None):
        """发送错误通知"""
        return self.send(message, title, channels, level="error")

    def success(self, message: str, title: str = "PerpBot 成功", channels: List[str] = None):
        """发送成功通知"""
        return self.send(message, title, channels, level="success")

    def trade_alert(self, symbol: str, action: str, price: float, size: float, pnl: float = None):
        """发送交易提醒"""
        if pnl is not None:
            pnl_str = f", PnL: {'+' if pnl >= 0 else ''}{pnl:.2f} USDC"
        else:
            pnl_str = ""

        message = f"{action.upper()} {symbol}: {size} @ ${price:.2f}{pnl_str}"
        level = "success" if pnl and pnl > 0 else "warning" if pnl and pnl < 0 else "info"
        return self.send(message, "交易提醒", level=level)

    def position_alert(self, symbol: str, side: str, entry: float, current: float, pnl_pct: float):
        """发送持仓提醒"""
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        message = f"{emoji} {symbol} {side.upper()}: 入场 ${entry:.2f} → 当前 ${current:.2f} ({pnl_pct:+.2%})"
        return self.send(message, "持仓更新", level="info")


# 全局通知服务实例
_notifier: Optional[NotificationService] = None


def get_notifier() -> NotificationService:
    """获取全局通知服务实例"""
    global _notifier
    if _notifier is None:
        _notifier = NotificationService()
    return _notifier


def notify(message: str, level: str = "info", channels: List[str] = None):
    """便捷函数：发送通知"""
    return get_notifier().send(message, level=level, channels=channels)
