# GRVT Exchange Setup Guide

## Overview
GRVT (formerly LedgerX) is a regulated derivatives exchange that supports perpetual futures trading. This guide will help you set up GRVT integration for the tw168 trading system.

## Prerequisites
- GRVT account with API access
- Python environment with required dependencies
- TradingView webhook alerts configured

## Step 1: Create GRVT Account
1. Visit [GRVT App](https://app.grvt.io/)
2. Complete KYC verification
3. Fund your account with USDT or other supported assets

## Step 2: Generate API Credentials
1. Log into your GRVT account
2. Navigate to API Settings
3. Create a new API key with the following permissions:
   - Trading: Read/Write
   - Account: Read
   - Orders: Read/Write
4. Note down your credentials:
   - **API Key**: Your public API key
   - **Private Key**: Your private key (keep this secure!)
   - **Trading Account ID**: Your account identifier

## Step 3: Configure Environment Variables
Edit your `.env` file and add the following variables:

```bash
# GRVT Exchange Configuration
GRVT_BASE_URL=https://api.grvt.io
GRVT_API_KEY=your_api_key_here
GRVT_PRIVATE_KEY=your_private_key_here
GRVT_TRADING_ACCOUNT_ID=your_trading_account_id_here
GRVT_ENV=mainnet

# Set GRVT as the active exchange (uncomment when ready)
# EXCHANGE=grvt
```

## Step 4: Test Connection
Run the test script to verify your setup:

```bash
cd /home/fordxx/perp-tools/_remote_tw168/tw168
python test_grvt_full_flow.py
```

Expected output:
- ✅ Connected successfully
- ✅ Last price for BTC-USDT-SWAP: $XXXX.XX
- ✅ Instrument info: {...}
- ✅ No position found (expected)
- ✅ Open orders count: 0

## Step 5: Enable Trading
Once testing passes, enable GRVT trading by uncommenting in `.env`:

```bash
EXCHANGE=grvt
```

## Step 6: Configure TradingView Webhooks
Set up your TradingView alerts to send webhooks to your tw168 service:

```
Webhook URL: http://your-server:8000/webhook/tradingview
Secret: your_webhook_secret
Message Format: JSON with type, instId, tf, zone, close, rsi fields
```

## Supported Trading Features
- ✅ Market and limit orders
- ✅ Stop-loss orders (conditional)
- ✅ Take-profit orders (conditional)
- ✅ Position management
- ✅ Real-time price feeds
- ✅ Risk management (ATR-based SL)
- ✅ RSI filtering
- ✅ Pattern recognition (W-bottom, Head & Shoulders)

## Symbol Mapping
GRVT uses standardized symbol formats:
- BTC/USDT → BTC_USDT_Perp
- ETH/USDT → ETH_USDT_Perp
- All symbols are automatically normalized

## Risk Management
- ATR-based stop-loss calculation
- Configurable risk per trade (USDT)
- Maximum position limits
- Emergency position closure

## Monitoring
- Telegram notifications for trades
- Position monitoring and alerts
- Error reporting and recovery

## Troubleshooting
1. **Connection Issues**: Verify API credentials and network connectivity
2. **Order Failures**: Check account balance and trading permissions
3. **Webhook Issues**: Ensure webhook URL is accessible and secret matches
4. **Position Sync**: Use emergency handler for stuck positions

## Security Notes
- Never share your private key
- Use environment variables for all sensitive data
- Enable 2FA on your GRVT account
- Regularly rotate API keys
- Monitor account activity

## Support
- GRVT Documentation: https://api-docs.grvt.io/
- GRVT Support: support@grvt.io
- Community: Discord/Telegram channels