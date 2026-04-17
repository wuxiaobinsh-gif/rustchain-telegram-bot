#!/usr/bin/env python3
"""
RustChain Telegram Bot
Checks wallet balance and miner status for RustChain network.
"""

import logging
import asyncio
from functools import partial
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters,
)
from telegram.constants import ParseMode

# Configuration
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
NODE_BASE_URL = "http://localhost:8080"
RTC_USD_PRICE = 0.10
RATE_LIMIT_SECONDS = 5

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# --- Rate Limiting ---
user_last_request: dict[int, float] = {}
lock = asyncio.Lock()


async def is_rate_limited(user_id: int) -> bool:
    """Check if user is rate limited. Returns True if limited."""
    async with lock:
        import time
        now = time.time()
        if user_id in user_last_request:
            elapsed = now - user_last_request[user_id]
            if elapsed < RATE_LIMIT_SECONDS:
                return True
        user_last_request[user_id] = now
        return False


# --- API Helpers ---
async def fetch_json(endpoint: str, timeout: int = 10) -> Optional[dict]:
    """Fetch JSON from node API with error handling."""
    import urllib.request
    import urllib.error
    import json

    url = f"{NODE_BASE_URL}{endpoint}"
    try:
        req = urllib.request.Request(url)
        with await asyncio.to_thread(
            urllib.request.urlopen, req, timeout=timeout
        ) as response:
            return json.loads(response.read().decode())
    except urllib.error.URLError as e:
        logger.error(f"Node unreachable: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from node: {e}")
        return None


async def check_node_health() -> bool:
    """Check if RustChain node is online."""
    data = await fetch_json("/health")
    return data is not None


# --- Command Handlers ---
async def cmd_start(update: Update, context: CallbackContext) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "Welcome to RustChain Bot!\n"
        "Use /help to see available commands."
    )


async def cmd_help(update: Update, context: CallbackContext) -> None:
    """Handle /help command."""
    help_text = (
        "<b>RustChain Bot Commands</b>\n\n"
        "/balance <i>&lt;wallet_id&gt;</i> - Check wallet balance\n"
        "/miners - List active miners\n"
        "/epoch - Show current epoch\n"
        "/price - Show RTC/USD price\n"
        "/help - Show this help message\n\n"
        "<i>Rate limit: 1 request per 5 seconds</i>"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def cmd_balance(update: Update, context: CallbackContext) -> None:
    """Handle /balance <wallet> command."""
    user_id = update.effective_user.id

    if await is_rate_limited(user_id):
        await update.message.reply_text(
            "⏳ Rate limited. Please wait 5 seconds between requests."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /balance <wallet_id>\nExample: /balance miner123"
        )
        return

    wallet_id = context.args[0]

    if not await check_node_health():
        await update.message.reply_text(
            "❌ Node is offline. Cannot fetch balance."
        )
        return

    data = await fetch_json(f"/wallet/balance?miner_id={wallet_id}")
    if data is None:
        await update.message.reply_text(
            f"❌ Could not fetch balance for wallet: {wallet_id}"
        )
        return

    balance = data.get("balance", "N/A")
    await update.message.reply_text(
        f"💰 <b>Wallet:</b> {wallet_id}\n"
        f"💵 <b>Balance:</b> {balance} RTC",
        parse_mode=ParseMode.HTML,
    )


async def cmd_miners(update: Update, context: CallbackContext) -> None:
    """Handle /miners command."""
    user_id = update.effective_user.id

    if await is_rate_limited(user_id):
        await update.message.reply_text(
            "⏳ Rate limited. Please wait 5 seconds between requests."
        )
        return

    if not await check_node_health():
        await update.message.reply_text(
            "❌ Node is offline. Cannot fetch miners list."
        )
        return

    data = await fetch_json("/api/miners")
    if data is None:
        await update.message.reply_text(
            "❌ Could not fetch miners list."
        )
        return

    miners = data.get("miners", [])
    if not miners:
        await update.message.reply_text(
            "ℹ️ No active miners found."
        )
        return

    miner_list = "\n".join(
        f"  • {m.get('id', 'unknown')} - {m.get('status', 'unknown')}"
        for m in miners
    )
    await update.message.reply_text(
        f"⛏️ <b>Active Miners ({len(miners)})</b>\n{miner_list}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_epoch(update: Update, context: CallbackContext) -> None:
    """Handle /epoch command."""
    user_id = update.effective_user.id

    if await is_rate_limited(user_id):
        await update.message.reply_text(
            "⏳ Rate limited. Please wait 5 seconds between requests."
        )
        return

    if not await check_node_health():
        await update.message.reply_text(
            "❌ Node is offline. Cannot fetch epoch."
        )
        return

    data = await fetch_json("/epoch")
    if data is None:
        await update.message.reply_text(
            "❌ Could not fetch current epoch."
        )
        return

    epoch = data.get("epoch", "N/A")
    block = data.get("block", "N/A")
    await update.message.reply_text(
        f"📊 <b>Epoch Info</b>\n"
        f"Epoch: {epoch}\n"
        f"Block: {block}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_price(update: Update, context: CallbackContext) -> None:
    """Handle /price command."""
    user_id = update.effective_user.id

    if await is_rate_limited(user_id):
        await update.message.reply_text(
            "⏳ Rate limited. Please wait 5 seconds between requests."
        )
        return

    await update.message.reply_text(
        f"💲 <b>RTC/USD Price</b>\n"
        f"${RTC_USD_PRICE:.2f} per RTC",
        parse_mode=ParseMode.HTML,
    )


async def error_handler(update: Update, context: CallbackContext) -> None:
    """Handle unexpected errors."""
    logger.error(f"Exception: {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "❌ An unexpected error occurred. Please try again."
        )


def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("miners", cmd_miners))
    application.add_handler(CommandHandler("epoch", cmd_epoch))
    application.add_handler(CommandHandler("price", cmd_price))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_error_handler(error_handler)

    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
