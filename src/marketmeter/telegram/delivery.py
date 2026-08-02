"""
telegram/delivery — message delivery utilities (send_to_owner, broadcast, send_report_to_all).
"""
from __future__ import annotations

import asyncio

from telegram.ext import Application
from telegram.error import Forbidden, TelegramError

from marketmeter.core.config import (
    OWNER_CHAT_ID, TELEGRAM_API_BASE_URL,
)
from marketmeter.core.logging import get_logger
from marketmeter.db import get_active_subscribers, get_subscriber_count
from marketmeter.reports import (
    generate_morning_report,
)
from marketmeter.telegram.rich.send import _send_rich_chunks

logger = get_logger(__name__)


async def send_to_owner(app: Application, message: str, use_rich: bool = False):
    """
    Send a message to the bot owner.

    use_rich routes through sendRichMessage so tables, **bold** and <details>
    render as native blocks. The scheduler already passed use_rich=True, but the
    parameter did not exist, so every scheduled notification raised TypeError.
    Content with Rich-only syntax is auto-detected too, because sending it with
    parse_mode="Markdown" strips the markers and dumps raw table pipes.
    """
    try:
        if use_rich or message is not None and ('**' in message or '<details' in message or '|' in message.split('\n')[0]):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, message)
        else:
            await app.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=message,
                parse_mode="Markdown",
            )
        logger.info("Sent notification to owner (%d)", OWNER_CHAT_ID)
    except TelegramError as e:
        logger.error(
            "Failed to send message to owner: %s. Verify the local Bot API server "
            "is reachable at %s and MARKETMETER_OWNER_CHAT_ID is correct.",
            e, TELEGRAM_API_BASE_URL,
        )


async def broadcast_to_subscribers(app: Application, message: str):
    """
    Send a message to all active subscribers.
    Handles blocked users and rate limits gracefully.
    """
    subscribers = get_active_subscribers()
    total = len(subscribers)

    if total == 0:
        logger.info("No active subscribers to broadcast to")
        return {'sent': 0, 'failed': 0, 'total': 0}

    logger.info("Broadcasting to %d subscribers...", total)
    sent = 0
    failed = 0

    for i, sub in enumerate(subscribers, 1):
        chat_id = sub['chat_id']
        try:
            # The morning report is Rich Markdown. Sending it with
            # parse_mode="Markdown" delivered stripped bold and raw table pipes.
            if '**' in message or '<details' in message or '|' in message.split('\n')[0]:
                await _send_rich_chunks(app.bot, chat_id, message,
                                       disable_notification=True)
            else:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown",
                    disable_notification=True,
                )
            sent += 1
        except Forbidden:
            # User blocked the bot — DO NOT auto-deactivate.
            # Only explicit /unsubscribe should stop reports.
            # Log and skip this user for this broadcast.
            logger.warning("Subscriber %d blocked bot, skipping broadcast (NOT deactivating)", chat_id)
            failed += 1
        except TelegramError as e:
            logger.warning("Failed to send to %d: %s", chat_id, e)
            failed += 1

        # Rate limiting: Telegram allows ~30 messages/second
        if i % 25 == 0:
            await asyncio.sleep(1)

        if i % 100 == 0:
            logger.info("Broadcast progress: %d/%d", i, total)

    logger.info("Broadcast complete: %d sent, %d failed, %d total", sent, failed, total)
    return {'sent': sent, 'failed': failed, 'total': total}


async def send_report_to_all(app: Application):
    """
    Generate and broadcast the morning report to all subscribers.
    Also sends a copy to the owner.
    """
    logger.info("Generating morning report for broadcast...")

    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(None, generate_morning_report)

    # Send to subscribers
    result = await broadcast_to_subscribers(app, report)

    # Send confirmation to owner
    sub_count = get_subscriber_count()
    owner_msg = (
        f"📊 *Morning Report Sent*\n"
        f"• Sent: {result['sent']}\n"
        f"• Failed: {result['failed']}\n"
        f"• Total subscribers: {sub_count}"
    )
    await send_to_owner(app, owner_msg)

    return result


__all__ = [
    "send_to_owner",
    "broadcast_to_subscribers",
    "send_report_to_all",
]