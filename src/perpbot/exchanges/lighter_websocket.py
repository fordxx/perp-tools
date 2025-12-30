"""Lighter DEX WebSocket client.

Implements real-time data streaming for:
- Order book updates
- Trade executions
- Account positions
- Order updates
- Account balances
- Transaction history

Reference: https://apidocs.lighter.xyz/docs/websocket-reference
"""
import asyncio
import json
import logging
import time
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass

import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


@dataclass
class WebSocketSubscription:
    """WebSocket subscription configuration."""
    channel: str
    auth_token: Optional[str] = None
    callback: Optional[Callable] = None


class LighterWebSocketClient:
    """Lighter DEX WebSocket client for real-time data."""

    def __init__(
        self,
        ws_url: str,
        account_id: Optional[int] = None,
        auth_token: Optional[str] = None,
    ):
        """Initialize WebSocket client.

        Args:
            ws_url: WebSocket endpoint (wss://mainnet.zklighter.elliot.ai/stream)
            account_id: Account index for private channels
            auth_token: Authentication token for protected channels
        """
        self.ws_url = ws_url
        self.account_id = account_id
        self.auth_token = auth_token

        self._ws: Optional[WebSocketClientProtocol] = None
        self._connected = False
        self._subscriptions: Dict[str, WebSocketSubscription] = {}
        self._callbacks: Dict[str, List[Callable]] = {}

        # Event loop management
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

        # Reconnection settings
        self._reconnect_delay = 5
        self._max_reconnect_delay = 60

        # Heartbeat settings (Lighter uses JSON ping/pong, not WebSocket protocol)
        self._heartbeat_interval = 30  # Send pong every 30 seconds
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._last_message_time = 0

    async def connect(self, start_message_loop: bool = True) -> None:
        """Connect to Lighter WebSocket.

        Args:
            start_message_loop: Whether to start a new message loop (default True).
                               Set to False when reconnecting from within an existing loop.
        """
        try:
            logger.info("🔌 Connecting to Lighter WebSocket: %s", self.ws_url)

            # Lighter uses JSON ping/pong, not WebSocket protocol ping/pong
            # So we disable the protocol-level ping (ping_interval=None)
            self._ws = await websockets.connect(
                self.ws_url,
                ping_interval=None,  # Disable protocol ping (Lighter doesn't respond)
                ping_timeout=None,
            )

            self._connected = True
            self._running = True
            self._last_message_time = time.time()

            logger.info("✅ Lighter WebSocket connected")

            # Resubscribe to all channels
            await self._resubscribe_all()

            # Start message handling loop (only if not reconnecting from within existing loop)
            if start_message_loop:
                asyncio.create_task(self._message_loop())
                # Start heartbeat task (JSON ping/pong every 30s)
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        except Exception as e:
            logger.error("❌ Failed to connect Lighter WebSocket: %s", e)
            self._connected = False
            raise

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        logger.info("Disconnecting Lighter WebSocket...")
        self._running = False
        self._connected = False

        # Cancel heartbeat task
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        logger.info("Lighter WebSocket disconnected")

    async def subscribe(
        self,
        channel: str,
        callback: Optional[Callable] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        """Subscribe to a WebSocket channel.

        Args:
            channel: Channel name (e.g., "order_book/1", "account_all/694324")
            callback: Optional callback function for messages
            auth_token: Optional auth token for protected channels

        Examples:
            # Public channels
            await ws.subscribe("order_book/1", on_orderbook_update)
            await ws.subscribe("trade/1", on_trade)

            # Private channels (require auth)
            await ws.subscribe(
                "account_all_positions/694324",
                on_position_update,
                auth_token=token
            )
        """
        subscription = WebSocketSubscription(
            channel=channel,
            auth_token=auth_token or self.auth_token,
            callback=callback,
        )

        self._subscriptions[channel] = subscription

        if callback:
            if channel not in self._callbacks:
                self._callbacks[channel] = []
            self._callbacks[channel].append(callback)

        # Send subscription message
        if self._connected and self._ws:
            await self._send_subscribe(subscription)

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel.

        Args:
            channel: Channel name to unsubscribe from
        """
        if channel in self._subscriptions:
            del self._subscriptions[channel]

        if channel in self._callbacks:
            del self._callbacks[channel]

        if self._connected and self._ws:
            message = {
                "type": "unsubscribe",
                "channel": channel,
            }
            await self._ws.send(json.dumps(message))
            logger.info("📤 Unsubscribed from: %s", channel)

    async def _send_subscribe(self, subscription: WebSocketSubscription) -> None:
        """Send subscription message to WebSocket."""
        if not self._ws:
            return

        message = {
            "type": "subscribe",
            "channel": subscription.channel,
        }

        # Add auth token for protected channels
        if subscription.auth_token:
            message["auth"] = subscription.auth_token

        await self._ws.send(json.dumps(message))
        logger.info("📤 Subscribed to: %s", subscription.channel)

    async def _resubscribe_all(self) -> None:
        """Resubscribe to all channels after reconnection."""
        for subscription in self._subscriptions.values():
            try:
                await self._send_subscribe(subscription)
            except Exception as e:
                logger.error("Failed to resubscribe to %s: %s", subscription.channel, e)

    async def _message_loop(self) -> None:
        """Main message receiving loop."""
        try:
            while self._running and self._ws:
                try:
                    message = await asyncio.wait_for(self._ws.recv(), timeout=30.0)
                    await self._handle_message(message)

                except asyncio.TimeoutError:
                    # No message in 30s, continue
                    continue

                except websockets.ConnectionClosed:
                    logger.warning("⚠️  Lighter WebSocket connection closed")
                    self._connected = False

                    if self._running:
                        await self._reconnect()
                        # After reconnect, continue the loop
                        continue
                    else:
                        break

        except Exception as e:
            logger.error("❌ Error in Lighter WebSocket message loop: %s", e)
            self._connected = False

            if self._running:
                await self._reconnect()

    async def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message.

        Args:
            message: JSON message string
        """
        try:
            data = json.loads(message)

            # Update last message time for heartbeat monitoring
            self._last_message_time = time.time()

            # Extract message type
            msg_type = data.get("type")

            # Lighter uses JSON ping/pong heartbeat (not WebSocket protocol)
            # Server sends {"type": "ping"}, client must reply {"type": "pong"}
            if msg_type == "ping":
                await self._send_pong()
                logger.debug("📡 Received ping, sent pong")
                return

            # Extract channel from message
            channel = data.get("channel")

            if not channel:
                logger.debug("Received message without channel: %s", msg_type)
                return

            # Call registered callbacks
            if channel in self._callbacks:
                for callback in self._callbacks[channel]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(data)
                        else:
                            callback(data)
                    except Exception as e:
                        logger.error("Error in callback for %s: %s", channel, e)

        except json.JSONDecodeError as e:
            logger.error("Failed to decode message: %s", e)
        except Exception as e:
            logger.error("Error handling message: %s", e)

    async def _reconnect(self) -> None:
        """Reconnect to WebSocket with exponential backoff.

        Note: This is called from within _message_loop, so we must NOT
        start a new message loop when reconnecting.
        """
        delay = self._reconnect_delay

        while self._running and not self._connected:
            try:
                logger.info("🔄 Reconnecting to Lighter WebSocket in %ds...", delay)
                await asyncio.sleep(delay)

                # Reconnect without starting a new message loop
                # (the existing loop will continue after this returns)
                await self.connect(start_message_loop=False)

                # Reset delay on successful connection
                delay = self._reconnect_delay
                break

            except Exception as e:
                logger.error("Reconnection failed: %s", e)

                # Exponential backoff
                delay = min(delay * 2, self._max_reconnect_delay)

    async def _send_pong(self) -> None:
        """Send JSON pong message to server.

        Lighter uses application-layer heartbeat with JSON messages:
        Server sends {"type": "ping"}, client responds with {"type": "pong"}

        This prevents the 120-second idle timeout that causes disconnections.
        """
        if self._ws and self._connected:
            try:
                pong_msg = json.dumps({"type": "pong"})
                await self._ws.send(pong_msg)
            except Exception as e:
                logger.error("❌ Failed to send pong: %s", e)

    async def _heartbeat_loop(self) -> None:
        """Proactive heartbeat loop - sends pong every 30 seconds.

        Lighter WebSocket has a 120-second idle timeout. By proactively
        sending pong messages every 30 seconds, we prevent disconnections
        even during periods of low market activity.

        This is critical because Lighter uses JSON {"type":"ping/pong"}
        instead of WebSocket protocol-level ping/pong frames.
        """
        logger.info("💓 Lighter heartbeat loop started (interval: %ds)", self._heartbeat_interval)

        try:
            while self._running and self._connected:
                await asyncio.sleep(self._heartbeat_interval)

                if self._connected and self._ws:
                    try:
                        await self._send_pong()
                        logger.debug("💓 Heartbeat pong sent (keepalive)")
                    except Exception as e:
                        logger.error("❌ Heartbeat failed: %s", e)
                        # Connection may be dead, let message loop handle reconnection
                        break

        except asyncio.CancelledError:
            logger.info("💓 Heartbeat loop cancelled")
        except Exception as e:
            logger.error("❌ Error in heartbeat loop: %s", e)

    # Convenience methods for common subscriptions

    async def subscribe_orderbook(
        self,
        market_id: int,
        callback: Callable,
    ) -> None:
        """Subscribe to order book updates for a market.

        Updates every 50ms with latest asks/bids.

        Args:
            market_id: Market ID (e.g., 1 for ETH)
            callback: Function to call with orderbook data
        """
        await self.subscribe(f"order_book/{market_id}", callback)

    async def subscribe_trades(
        self,
        market_id: int,
        callback: Callable,
    ) -> None:
        """Subscribe to trade executions for a market.

        Args:
            market_id: Market ID
            callback: Function to call with trade data
        """
        await self.subscribe(f"trade/{market_id}", callback)

    async def subscribe_market_stats(
        self,
        market_id: int,
        callback: Callable,
    ) -> None:
        """Subscribe to market statistics.

        Args:
            market_id: Market ID (or "all" for all markets)
            callback: Function to call with market stats
        """
        channel = f"market_stats/{market_id}" if market_id != "all" else "market_stats/all"
        await self.subscribe(channel, callback)

    async def subscribe_account_positions(
        self,
        callback: Callable,
        auth_token: Optional[str] = None,
    ) -> None:
        """Subscribe to account position updates.

        Requires authentication.

        Args:
            callback: Function to call with position data
            auth_token: Optional auth token (uses default if not provided)
        """
        if not self.account_id:
            raise ValueError("Account ID required for account subscriptions")

        await self.subscribe(
            f"account_all_positions/{self.account_id}",
            callback,
            auth_token=auth_token,
        )

    async def subscribe_account_orders(
        self,
        callback: Callable,
        market_id: Optional[int] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        """Subscribe to account order updates.

        Requires authentication.

        Args:
            callback: Function to call with order data
            market_id: Optional market ID (all markets if not provided)
            auth_token: Optional auth token
        """
        if not self.account_id:
            raise ValueError("Account ID required for account subscriptions")

        if market_id:
            channel = f"account_orders/{market_id}/{self.account_id}"
        else:
            channel = f"account_all_orders/{self.account_id}"

        await self.subscribe(channel, callback, auth_token=auth_token)

    async def subscribe_account_all(
        self,
        callback: Callable,
        auth_token: Optional[str] = None,
    ) -> None:
        """Subscribe to all account updates (positions, trades, assets, funding).

        Requires authentication.

        Args:
            callback: Function to call with account data
            auth_token: Optional auth token
        """
        if not self.account_id:
            raise ValueError("Account ID required for account subscriptions")

        await self.subscribe(
            f"account_all/{self.account_id}",
            callback,
            auth_token=auth_token,
        )

    async def subscribe_user_stats(
        self,
        callback: Callable,
        auth_token: Optional[str] = None,
    ) -> None:
        """Subscribe to user statistics (collateral, leverage, margin).

        Requires authentication.

        Args:
            callback: Function to call with user stats
            auth_token: Optional auth token
        """
        if not self.account_id:
            raise ValueError("Account ID required for account subscriptions")

        await self.subscribe(
            f"user_stats/{self.account_id}",
            callback,
            auth_token=auth_token,
        )

    async def subscribe_notifications(
        self,
        callback: Callable,
        auth_token: Optional[str] = None,
    ) -> None:
        """Subscribe to notifications (liquidations, deleveraging, announcements).

        Requires authentication.

        Args:
            callback: Function to call with notifications
            auth_token: Optional auth token
        """
        if not self.account_id:
            raise ValueError("Account ID required for account subscriptions")

        await self.subscribe(
            f"notification/{self.account_id}",
            callback,
            auth_token=auth_token,
        )


# Helper function for standalone usage
async def create_lighter_websocket(
    mainnet: bool = True,
    account_id: Optional[int] = None,
    auth_token: Optional[str] = None,
) -> LighterWebSocketClient:
    """Create and connect a Lighter WebSocket client.

    Args:
        mainnet: True for mainnet, False for testnet
        account_id: Account ID for private channels
        auth_token: Auth token for protected channels

    Returns:
        Connected WebSocket client

    Example:
        ws = await create_lighter_websocket(
            mainnet=True,
            account_id=694324,
            auth_token="your-token"
        )

        # Subscribe to orderbook
        await ws.subscribe_orderbook(1, lambda data: print(data))

        # Keep running
        await asyncio.sleep(3600)

        # Cleanup
        await ws.disconnect()
    """
    ws_url = (
        "wss://mainnet.zklighter.elliot.ai/stream" if mainnet
        else "wss://testnet.zklighter.elliot.ai/stream"
    )

    client = LighterWebSocketClient(ws_url, account_id, auth_token)
    await client.connect()

    return client
