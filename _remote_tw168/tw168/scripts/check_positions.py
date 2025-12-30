#!/usr/bin/env python3
"""Position health check script - verifies stop-loss protection on all open positions.

Usage:
    python scripts/check_positions.py [--alert-webhook URL]

Exit codes:
    0 - All positions are protected
    1 - Unprotected positions found
    2 - Script error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class PositionHealth:
    """Health status of a single position."""
    inst_id: str
    pos_side: str
    size: str
    avg_px: float
    mark_px: float
    unrealized_pnl: float
    has_sl: bool
    sl_trigger_px: float | None
    risk_r: float | None  # Risk as R-multiple
    status: str  # ok | warning | critical


def _load_env() -> dict[str, str]:
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return {}

    env_vars = {}
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def _get_okx_client():
    """Create OKX client from environment variables."""
    env_vars = _load_env()

    # Load environment
    for key, value in env_vars.items():
        if key not in os.environ:
            os.environ[key] = value

    # Import after environment is set
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.config import SETTINGS
    from app.okx import OKXClient, OKXCredentials

    if not all([SETTINGS.okx_api_key, SETTINGS.okx_api_secret, SETTINGS.okx_api_passphrase]):
        print("ERROR: OKX credentials not configured", file=sys.stderr)
        sys.exit(2)

    creds = OKXCredentials(
        api_key=SETTINGS.okx_api_key,
        api_secret=SETTINGS.okx_api_secret,
        passphrase=SETTINGS.okx_api_passphrase,
    )

    return OKXClient(base_url=SETTINGS.okx_base_url, creds=creds, enable_rate_limit=False)


def _get_all_positions(client) -> list[dict]:
    """Get all open positions from OKX."""
    try:
        resp = client.request("GET", "/api/v5/account/positions")
        positions = resp.get("data", [])

        # Filter only positions with non-zero size
        return [
            pos for pos in positions
            if pos.get("pos") and float(pos.get("pos", "0")) != 0
        ]
    except Exception as e:
        print(f"ERROR: Failed to fetch positions: {e}", file=sys.stderr)
        sys.exit(2)


def _get_algo_orders(client, inst_id: str) -> list[dict]:
    """Get active algo orders (stop-loss, take-profit) for an instrument."""
    try:
        resp = client.request(
            "GET",
            "/api/v5/trade/orders-algo-pending",
            params={"instId": inst_id, "ordType": "conditional"}
        )
        return resp.get("data", [])
    except Exception as e:
        print(f"WARNING: Failed to fetch algo orders for {inst_id}: {e}", file=sys.stderr)
        return []


def _check_position_health(position: dict, algo_orders: list[dict]) -> PositionHealth:
    """Check if position has proper stop-loss protection."""
    inst_id = position.get("instId", "")
    pos_side = position.get("posSide", "").lower()
    pos = float(position.get("pos", "0"))
    avg_px = float(position.get("avgPx", "0"))
    mark_px = float(position.get("markPx", "0"))
    upnl = float(position.get("upl", "0"))

    # Find stop-loss order for this position
    sl_order = None
    for order in algo_orders:
        ord_pos_side = order.get("posSide", "").lower()
        if ord_pos_side == pos_side and order.get("slTriggerPx"):
            sl_order = order
            break

    has_sl = sl_order is not None
    sl_trigger_px = float(sl_order.get("slTriggerPx", "0")) if sl_order else None

    # Calculate risk as R-multiple
    risk_r = None
    status = "ok"

    if has_sl and sl_trigger_px and avg_px > 0:
        if pos_side == "long":
            stop_distance = avg_px - sl_trigger_px
            current_distance = mark_px - avg_px
        else:  # short
            stop_distance = sl_trigger_px - avg_px
            current_distance = avg_px - mark_px

        if stop_distance > 0:
            risk_r = current_distance / stop_distance

            # Determine status based on risk
            if risk_r < -0.5:  # Losing more than 0.5R
                status = "warning"
            elif risk_r < -1.0:  # Losing more than 1R (stop should have triggered)
                status = "critical"
    else:
        status = "critical"  # No stop-loss protection

    return PositionHealth(
        inst_id=inst_id,
        pos_side=pos_side,
        size=str(abs(pos)),
        avg_px=avg_px,
        mark_px=mark_px,
        unrealized_pnl=upnl,
        has_sl=has_sl,
        sl_trigger_px=sl_trigger_px,
        risk_r=risk_r,
        status=status,
    )


def _send_alert(webhook_url: str, message: str) -> None:
    """Send alert to webhook (e.g., Telegram, Discord, Slack)."""
    try:
        requests.post(webhook_url, json={"text": message}, timeout=5)
    except Exception as e:
        print(f"WARNING: Failed to send alert: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check position health and stop-loss protection")
    parser.add_argument("--alert-webhook", help="Webhook URL for alerts")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    client = _get_okx_client()
    positions = _get_all_positions(client)

    if not positions:
        if args.json:
            print(json.dumps({"status": "ok", "positions": [], "message": "No open positions"}))
        else:
            print("✅ No open positions")
        return 0

    # Check health of each position
    health_checks = []
    for pos in positions:
        inst_id = pos.get("instId", "")
        algo_orders = _get_algo_orders(client, inst_id)
        health = _check_position_health(pos, algo_orders)
        health_checks.append(health)

    # Categorize positions
    critical = [h for h in health_checks if h.status == "critical"]
    warning = [h for h in health_checks if h.status == "warning"]
    ok = [h for h in health_checks if h.status == "ok"]

    # Generate report
    if args.json:
        report = {
            "status": "critical" if critical else ("warning" if warning else "ok"),
            "timestamp": time.time(),
            "total_positions": len(positions),
            "critical": len(critical),
            "warning": len(warning),
            "ok": len(ok),
            "positions": [
                {
                    "inst_id": h.inst_id,
                    "pos_side": h.pos_side,
                    "size": h.size,
                    "avg_px": h.avg_px,
                    "mark_px": h.mark_px,
                    "unrealized_pnl": h.unrealized_pnl,
                    "has_sl": h.has_sl,
                    "sl_trigger_px": h.sl_trigger_px,
                    "risk_r": h.risk_r,
                    "status": h.status,
                }
                for h in health_checks
            ],
        }
        print(json.dumps(report, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"POSITION HEALTH CHECK - {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        print(f"Total Positions: {len(positions)}")
        print(f"✅ Protected: {len(ok)}")
        print(f"⚠️  Warning: {len(warning)}")
        print(f"❌ Critical: {len(critical)}")
        print(f"{'='*60}\n")

        # Show critical positions first
        if critical:
            print("❌ CRITICAL POSITIONS (No SL or Stop Overrun):")
            print(f"{'Instrument':<20} {'Side':<6} {'Size':<12} {'Avg Price':<12} {'Mark Price':<12} {'PnL':<12} {'SL':<12} {'Risk R':<8}")
            print("-" * 110)
            for h in critical:
                sl_str = f"{h.sl_trigger_px:.4f}" if h.sl_trigger_px else "NONE"
                risk_str = f"{h.risk_r:.2f}R" if h.risk_r else "N/A"
                pnl_str = f"${h.unrealized_pnl:.2f}"
                print(f"{h.inst_id:<20} {h.pos_side:<6} {h.size:<12} {h.avg_px:<12.4f} {h.mark_px:<12.4f} {pnl_str:<12} {sl_str:<12} {risk_str:<8}")
            print()

        # Show warning positions
        if warning:
            print("⚠️  WARNING POSITIONS (Losing > 0.5R):")
            print(f"{'Instrument':<20} {'Side':<6} {'Size':<12} {'Avg Price':<12} {'Mark Price':<12} {'PnL':<12} {'SL':<12} {'Risk R':<8}")
            print("-" * 110)
            for h in warning:
                sl_str = f"{h.sl_trigger_px:.4f}" if h.sl_trigger_px else "NONE"
                risk_str = f"{h.risk_r:.2f}R" if h.risk_r else "N/A"
                pnl_str = f"${h.unrealized_pnl:.2f}"
                print(f"{h.inst_id:<20} {h.pos_side:<6} {h.size:<12} {h.avg_px:<12.4f} {h.mark_px:<12.4f} {pnl_str:<12} {sl_str:<12} {risk_str:<8}")
            print()

        # Show healthy positions
        if ok:
            print("✅ HEALTHY POSITIONS:")
            print(f"{'Instrument':<20} {'Side':<6} {'Size':<12} {'Avg Price':<12} {'Mark Price':<12} {'PnL':<12} {'SL':<12} {'Risk R':<8}")
            print("-" * 110)
            for h in ok:
                sl_str = f"{h.sl_trigger_px:.4f}" if h.sl_trigger_px else "NONE"
                risk_str = f"{h.risk_r:.2f}R" if h.risk_r else "N/A"
                pnl_str = f"${h.unrealized_pnl:.2f}"
                print(f"{h.inst_id:<20} {h.pos_side:<6} {h.size:<12} {h.avg_px:<12.4f} {h.mark_px:<12.4f} {pnl_str:<12} {sl_str:<12} {risk_str:<8}")
            print()

    # Send alerts if configured
    if args.alert_webhook and (critical or warning):
        alert_msg = f"🚨 POSITION HEALTH ALERT\n\n"
        alert_msg += f"Total Positions: {len(positions)}\n"
        alert_msg += f"❌ Critical: {len(critical)}\n"
        alert_msg += f"⚠️ Warning: {len(warning)}\n\n"

        if critical:
            alert_msg += "Critical positions:\n"
            for h in critical:
                alert_msg += f"• {h.inst_id} {h.pos_side} - "
                if not h.has_sl:
                    alert_msg += "NO STOP-LOSS\n"
                else:
                    alert_msg += f"Stop overrun ({h.risk_r:.2f}R)\n"

        _send_alert(args.alert_webhook, alert_msg)

    # Return exit code
    if critical:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
