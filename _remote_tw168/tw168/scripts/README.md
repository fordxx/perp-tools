# Scripts Directory

This directory contains utility scripts for monitoring and maintaining the tw168 trading system.

## Position Health Check

### Overview

The position health check script monitors all open positions to ensure they have proper stop-loss protection and alerts you to any risky situations.

### Files

- `check_positions.py` - Main Python script for position health checks
- `check_positions.sh` - Bash wrapper for easier cron scheduling

### Features

- ✅ Verify all open positions have stop-loss orders
- ✅ Calculate risk in R-multiples (current P&L / stop distance)
- ✅ Detect positions without stop-loss protection
- ✅ Detect positions where stop-loss should have triggered (> -1R)
- ✅ Send alerts via webhook (Telegram, Discord, Slack, etc.)
- ✅ JSON output for programmatic integration
- ✅ Color-coded console output for quick scanning

### Usage

#### Manual Check (Console Output)

```bash
# Basic check
python scripts/check_positions.py

# With webhook alerts
python scripts/check_positions.py --alert-webhook https://your-webhook-url

# JSON output
python scripts/check_positions.py --json
```

#### Automated Monitoring (Cron)

Add to your crontab to check positions every hour:

```bash
# Edit crontab
crontab -e

# Add this line (check every hour)
0 * * * * /path/to/tw168/scripts/check_positions.sh --alert-webhook https://your-webhook-url >> /var/log/position_health.log 2>&1

# Or check every 30 minutes
*/30 * * * * /path/to/tw168/scripts/check_positions.sh --alert-webhook https://your-webhook-url >> /var/log/position_health.log 2>&1
```

### Output Examples

#### Console Output

```
============================================================
POSITION HEALTH CHECK - 2025-12-25 10:00:00
============================================================
Total Positions: 5
✅ Protected: 3
⚠️  Warning: 1
❌ Critical: 1
============================================================

❌ CRITICAL POSITIONS (No SL or Stop Overrun):
Instrument           Side   Size         Avg Price    Mark Price   PnL          SL           Risk R
--------------------------------------------------------------------------------------------------------------
ETH-USDT-SWAP        long   10           2000.0000    1950.0000    $-500.00     NONE         N/A

⚠️  WARNING POSITIONS (Losing > 0.5R):
Instrument           Side   Size         Avg Price    Mark Price   PnL          SL           Risk R
--------------------------------------------------------------------------------------------------------------
BTC-USDT-SWAP        long   1            50000.0000   49800.0000   $-200.00     49500.0000   -0.60R

✅ HEALTHY POSITIONS:
Instrument           Side   Size         Avg Price    Mark Price   PnL          SL           Risk R
--------------------------------------------------------------------------------------------------------------
SOL-USDT-SWAP        long   100          120.0000     125.0000     $+500.00     115.0000     1.00R
MATIC-USDT-SWAP      short  1000         0.8000       0.7800       $+200.00     0.8200       1.00R
AVAX-USDT-SWAP       long   50           30.0000      31.0000      $+50.00      28.0000      0.50R
```

#### JSON Output

```json
{
  "status": "warning",
  "timestamp": 1735117200.0,
  "total_positions": 5,
  "critical": 1,
  "warning": 1,
  "ok": 3,
  "positions": [
    {
      "inst_id": "ETH-USDT-SWAP",
      "pos_side": "long",
      "size": "10",
      "avg_px": 2000.0,
      "mark_px": 1950.0,
      "unrealized_pnl": -500.0,
      "has_sl": false,
      "sl_trigger_px": null,
      "risk_r": null,
      "status": "critical"
    }
  ]
}
```

### Health Status Definitions

| Status | Icon | Description |
|--------|------|-------------|
| **ok** | ✅ | Position has stop-loss protection and is losing < 0.5R |
| **warning** | ⚠️ | Position has stop-loss protection but is losing 0.5R - 1.0R |
| **critical** | ❌ | No stop-loss protection OR losing > 1.0R (stop should have triggered) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All positions are protected and healthy |
| 1 | Unprotected positions found or positions in warning/critical state |
| 2 | Script error (missing credentials, API error, etc.) |

### Webhook Integration

The script can send alerts to any webhook URL. Common integrations:

#### Telegram Bot

1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Get your chat ID
3. Use webhook URL: `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>`

#### Discord Webhook

1. Create a webhook in Discord server settings
2. Use the webhook URL provided by Discord

#### Slack Webhook

1. Create an incoming webhook in Slack
2. Use the webhook URL provided by Slack

### Requirements

- Python 3.12+
- Access to `.env` file with OKX credentials
- `requests` library (already in project dependencies)

### Troubleshooting

**Script exits with code 2**
- Check that your `.env` file exists and contains valid OKX credentials
- Verify OKX API key has permission to read positions

**No positions detected but you have open positions**
- Verify the OKX account matches your credentials
- Check that positions are in SWAP contracts (script filters by instType)

**False critical alerts**
- Positions may not have stop-loss attached if opened manually
- Extended DEX positions won't be detected (script is OKX-only)

### Related Files

- [app/metrics.py](../app/metrics.py) - Order metrics tracking
- [app/rate_limiter.py](../app/rate_limiter.py) - API rate limiting
- [BUG_FIXES.md](../BUG_FIXES.md#-额外防护措施-additional-protection) - Documentation of protection measures

---

## Telegram Notifications Setup

### Overview

The tw168 system can send real-time notifications to Telegram for important events like stop-loss failures, emergency closes, and trade executions.

### Files

- `setup_telegram.sh` - Interactive setup script for Telegram notifications

### Quick Setup

Run the interactive setup script on the remote server:

```bash
# SSH to server
ssh -i /home/fordxx/lightsail.pem ubuntu@3.38.98.169

# Run setup script
/home/ubuntu/tw168/scripts/setup_telegram.sh
```

The script will guide you through:
1. Getting a Bot Token from @BotFather
2. Getting your Chat ID
3. Testing the configuration
4. Automatically updating `.env` and restarting the service

### Manual Setup

If you prefer to configure manually, see [TELEGRAM_SETUP.md](../TELEGRAM_SETUP.md) for detailed instructions.

### What Gets Notified

Once configured, you'll receive notifications for:

**Error Notifications** (🔴 Critical)
- Stop-loss order failures
- Emergency close executions
- High stop-loss failure rate alerts (>5%)
- TP order failures

**Info Notifications** (🟢 Info)
- Successful entry orders with stop-loss protection
- TP orders successfully placed
- Position state changes

### Notification Format

All messages have the `[tw168]` prefix:

```
[tv168] ERROR Stop-loss order failed for ETH-USDT-SWAP, executing emergency close
[tv168] INFO ✅ Entry filled: BTC-USDT-SWAP LONG @ $50000.00, SL @ $49500.00
[tv168] ERROR ⚠️ HIGH SL FAILURE RATE: 8.3% (5/60 attempts)
```

### Testing Notifications

After setup, test that notifications work:

```bash
sudo docker exec -it tw168-tv-okx-1 python3 -c "
from app.notify import notify_info
notify_info('测试消息：配置成功！')
"
```

You should receive a message in Telegram within a few seconds.

### Troubleshooting

**No notifications received**

1. Check environment variables in container:
   ```bash
   sudo docker exec tw168-tv-okx-1 env | grep TELEGRAM
   ```

2. Verify bot token:
   ```bash
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
   ```

3. Make sure you sent `/start` to your bot first

4. Check Docker logs for errors:
   ```bash
   sudo docker logs tw168-tv-okx-1 --tail 50
   ```

**Bot can't send to group**

- Ensure bot is added to the group
- Group ID should be negative (e.g., `-1001234567890`)
- Bot needs permission to send messages

### Security

- Never share your Bot Token
- Keep `.env` file permissions restricted: `chmod 600 .env`
- Regenerate token via @BotFather if compromised

### Related Documentation

- [TELEGRAM_SETUP.md](../TELEGRAM_SETUP.md) - Detailed setup guide
- [Telegram Bot API](https://core.telegram.org/bots/api) - Official API docs
