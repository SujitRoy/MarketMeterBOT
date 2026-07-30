"""
Telegram bot for MarketMeter.
Handles commands, sends reports, and manages subscribers.
Uses python-telegram-bot v21.x with asyncio.
"""
import asyncio
import logging
import re
from datetime import date

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
)
from telegram.error import TelegramError, Forbidden

from config import (
    BOT_TOKEN, OWNER_CHAT_ID, OWNER_FIRST_NAME,
    TELEGRAM_API_BASE_URL, REPORT_CHUNK_MAX_CHARS, REPORT_CHUNK_DELAY,
    TELEGRAM_MAX_CHARS, RICH_MESSAGE_MAX_CHARS,
)
from database import (
    add_subscriber, remove_subscriber, get_active_subscribers,
    get_subscriber_count,
)
from report_generator import (
    generate_morning_report, generate_sync_status_message,
    generate_sync_failure_alert, generate_status_message,
    generate_welcome_message, generate_help_message,
    generate_indicators_message,
)

logger = logging.getLogger(__name__)


# ── Command Handlers ────────────────────────────────────────────────

async def _reply(update: Update, text: str) -> None:
    """
    Reply to a command, routing Rich Markdown through sendRichMessage.

    Every user-facing message now uses **bold**, which legacy Markdown V1 shows
    as literal asterisks, so all replies go through the rich path when they
    contain Rich-only syntax.
    """
    if _needs_rich(text):
        await _send_rich_chunks(update.get_bot(), update.effective_chat.id, text)
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    first_name = user.first_name or "there"
    await _reply(update, generate_welcome_message(first_name))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await _reply(update, generate_help_message())


async def cmd_indicators(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /indicators command - indicator glossary and scoring rules."""
    await _reply(update, generate_indicators_message())


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribe command."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    is_new = add_subscriber(
        chat_id=chat_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    if is_new:
        msg = (
            f"✅ **Subscribed successfully!**\n\n"
            f"You'll receive daily morning reports at 8:30 AM IST.\n"
            f"Use /unsubscribe to stop receiving reports."
        )
    else:
        msg = "ℹ️ You're already subscribed! Use /unsubscribe to stop."

    await _reply(update, msg)
    logger.info("Subscriber %s (%d) %s",
                user.username or user.first_name, chat_id,
                "added" if is_new else "already active")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unsubscribe command."""
    chat_id = update.effective_chat.id
    removed = remove_subscriber(chat_id)

    if removed:
        msg = (
            "👋 **Unsubscribed.**\n\n"
            "You'll no longer receive daily reports.\n"
            "Use /subscribe to re-subscribe anytime."
        )
    else:
        msg = "ℹ️ You weren't subscribed. Use /subscribe to start receiving reports."

    await _reply(update, msg)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /report command — send latest analysis on demand."""
    chat_id = update.effective_chat.id

    # Send temp message
    temp_msg = await update.message.reply_text("🔍 Generating report...")

    try:
        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        # Always use latest available analysis date (no arg = auto-detect)
        report = await loop.run_in_executor(None, generate_morning_report)

        # Delete temp message
        try:
            await temp_msg.delete()
        except Exception:
            pass

        # Send in chunks using Rich Messages
        await _send_report_in_chunks(update.message, report)

    except Exception as e:
        logger.error("Failed to generate report: %s", e)
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            "❌ Failed to generate report. Please try again later.\n"
            "Use /status to check if data is available."
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — show DB and sync status."""
    loop = asyncio.get_event_loop()
    msg = await loop.run_in_executor(None, generate_status_message)
    # The status message contains a recent-syncs table, which Markdown V1
    # renders as raw pipes.
    await _reply(update, msg)


# ── Bot Setup ───────────────────────────────────────────────────────

def create_application() -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(BOT_TOKEN).base_url(TELEGRAM_API_BASE_URL).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("indicators", cmd_indicators))

    logger.info("Bot application created with %d handlers", 7)
    return app


# ── Message Sending ─────────────────────────────────────────────────

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
        if use_rich or _needs_rich(message):
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
            if _needs_rich(message):
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
            # User blocked the bot — deactivate them
            logger.info("Subscriber %d blocked bot, deactivating", chat_id)
            remove_subscriber(chat_id)
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


# ── Rich Message Helper ─────────────────────────────────────────────

# A table separator row, e.g. "|:-:|:------|------:|". Used to locate the
# two-line header that must be repeated when a table spans chunks.
_TABLE_SEP_RE = re.compile(r'^\|[\s:\-|]+\|$')


def _needs_rich(text: str) -> bool:
    """
    True when text uses syntax legacy Markdown V1 cannot render.

    V1 has no tables, no <details>, and treats ** as literal, which is why the
    report arrived with bold markers stripped and raw table pipes visible.
    """
    if '**' in text or '<details' in text:
        return True
    return any(ln.startswith('|') for ln in text.split('\n'))


def _split_rich_markdown(text: str,
                         max_chars: int = REPORT_CHUNK_MAX_CHARS) -> list[str]:
    """
    Split Rich Markdown into chunks under Telegram's 4096-char cap.

    Splitting on length alone corrupts structure, so this keeps two invariants:

    * A <details> block is never cut open. A chunk ending mid-block would leave
      an unclosed tag and the next chunk would start with orphaned content.
    * A table that spans a boundary gets its header and separator rows repeated
      at the top of the continuation chunk. Without them the server sees plain
      pipe text and renders no table.
    """
    lines = text.split('\n')
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    details_depth = 0
    tbl_header: tuple[str, str] | None = None

    def flush() -> None:
        nonlocal cur, cur_len
        body = '\n'.join(cur).strip()
        if body:
            chunks.append(body)
        cur = []
        cur_len = 0

    for line in lines:
        stripped = line.strip()

        # Remember the active table header (previous line + this separator).
        if _TABLE_SEP_RE.match(stripped) and cur and cur[-1].lstrip().startswith('|'):
            tbl_header = (cur[-1], line)
        elif stripped and not stripped.startswith('|'):
            tbl_header = None  # non-table content ends the table

        cost = len(line) + 1

        # A <details> block must travel whole. Break *before* one starts if the
        # current chunk is already large, rather than discovering mid-block that
        # the hard ceiling has been hit and cutting the tag open.
        if (stripped.startswith('<details') and details_depth == 0 and cur
                and cur_len + cost > max_chars // 2):
            flush()

        over = cur_len + cost > max_chars
        # Only force a break inside <details> as an absolute last resort, when a
        # single block cannot fit a message on its own.
        hard_over = cur_len + cost > TELEGRAM_MAX_CHARS - 256

        if cur and (over or hard_over) and (details_depth == 0 or hard_over):
            resume_table = stripped.startswith('|') and tbl_header is not None
            flush()
            if resume_table:
                cur = [tbl_header[0], tbl_header[1]]
                cur_len = sum(len(x) + 1 for x in cur)

        cur.append(line)
        cur_len += cost

        if '<details' in line:
            details_depth += 1
        if '</details>' in line:
            details_depth = max(0, details_depth - 1)

    flush()

    # Last-resort guard so a chunk can never exceed the hard cap.
    safe: list[str] = []
    for ch in chunks:
        while len(ch) > TELEGRAM_MAX_CHARS:
            safe.append(ch[:TELEGRAM_MAX_CHARS])
            ch = ch[TELEGRAM_MAX_CHARS:]
        if ch:
            safe.append(ch)
    return safe or [text[:TELEGRAM_MAX_CHARS]]


async def _send_rich_message(bot, chat_id: int, markdown: str,
                              disable_notification: bool = False) -> dict:
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
    return await bot._post("sendRichMessage", payload, api_kwargs={})


async def _send_rich_chunks(bot, chat_id: int, markdown: str,
                           disable_notification: bool = False) -> int:
    """
    Send Rich Markdown as however many messages the 4096-char cap requires.

    Chunks are paced by REPORT_CHUNK_DELAY (1.0s) because Telegram throttles
    bursts to roughly one message per second per chat.
    """
    chunks = _split_rich_markdown(markdown)
    for i, chunk in enumerate(chunks, 1):
        await _send_rich_message(bot, chat_id, chunk,
                                 disable_notification=disable_notification)
        if i < len(chunks):
            await asyncio.sleep(REPORT_CHUNK_DELAY)
    logger.info("Sent %d rich chunk(s) to %d (%d chars)",
                len(chunks), chat_id, len(markdown))
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


# Re-export for external use
send_rich_message = _send_rich_message


# ── Helpers ─────────────────────────────────────────────────────────

def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split a long message into chunks at paragraph boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    paragraphs = text.split('\n\n')
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_len:
            current = (current + '\n\n' + para) if current else para
        else:
            if current:
                chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    return chunks
