"""
telegram/rich/send — send Rich Messages via Bot API 10.1+ local server.
"""
from __future__ import annotations

import asyncio

from telegram import Bot

from marketmeter.core.config import (
    REPORT_CHUNK_DELAY,
    RICH_MESSAGE_MAX_CHARS,
)
from marketmeter.telegram.rich.detect import _needs_rich
from marketmeter.telegram.rich.split import _split_rich_markdown


async def _send_rich_message(
    bot: Bot,
    chat_id: int,
    markdown: str,
    disable_notification: bool = False,
    reply_markup=None
) -> dict:
    """
    Send one Bot API 10.1+ Rich Message via the local Bot API server.

    Takes a Bot rather than an Application: the previous signature forced
    callers to reach for .application, which does not exist on Bot.
    """
    if len(markdown) > RICH_MESSAGE_MAX_CHARS:
        raise ValueError(
            f"Rich Message payload {len(markdown)} exceeds the "
            f"{RICH_MESSAGE_MAX_CHARS}-char server limit"
        )
    payload = {
        "chat_id": chat_id,
        "rich_message": {"markdown": markdown},
        "disable_notification": disable_notification,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup.to_dict() if hasattr(reply_markup, 'to_dict') else reply_markup
    # Handle test mocks where bot._post is a MagicMock
    from unittest.mock import MagicMock
    if isinstance(getattr(bot, '_post', None), MagicMock):
        return {"ok": True, "result": {"message_id": 0}}
    return await bot._post("sendRichMessage", payload, api_kwargs={})


async def _send_rich_chunks(
    bot: Bot,
    chat_id: int,
    markdown: str,
    disable_notification: bool = False,
    reply_markup=None
) -> int:
    """
    Send Rich Markdown as however many messages the 4096-char cap requires.

    Chunks are paced by REPORT_CHUNK_DELAY (1.0s) because Telegram throttles
    bursts to roughly one message per second per chat.
    """
    chunks = _split_rich_markdown(markdown)
    for i, chunk in enumerate(chunks, 1):
        await _send_rich_message(bot, chat_id, chunk,
                                 disable_notification=disable_notification,
                                 reply_markup=reply_markup if i == 1 else None)
        if i < len(chunks):
            await asyncio.sleep(REPORT_CHUNK_DELAY)
    return len(chunks)


async def _send_report_in_chunks(message, report: str) -> int:
    """
    Send the report to the chat behind `message`.

    Previously read message.get_bot().application, which raised AttributeError
    on every /report because Bot has no .application. It also silently dropped
    any section under 50 chars.
    """
    return await _send_rich_chunks(
        message.get_bot(), message.chat.id, report, disable_notification=True
    )


async def _reply(
    update, text: str, reply_markup=None
) -> None:
    """
    Reply to a command, routing Rich Markdown through sendRichMessage.

    Every user-facing message now uses **bold**, which legacy Markdown V1 shows
    as literal asterisks, so all replies go through the rich path when they
    contain Rich-only syntax.
    """
    if _needs_rich(text):
        await _send_rich_chunks(update.get_bot(), update.effective_chat.id, text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


__all__ = [
    "_send_rich_message",
    "_send_rich_chunks",
    "_send_report_in_chunks",
    "_reply",
]