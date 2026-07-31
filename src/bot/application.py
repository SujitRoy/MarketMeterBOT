"""
Bot Application Setup
Creates and configures the Telegram bot application.
"""
import logging

from telegram.ext import Application, ApplicationBuilder
from telegram.request import HTTPXRequest

from src.core.config import BOT_TOKEN
from src.core.logging import setup_logging

logger = logging.getLogger(__name__)


def create_application(
    token: str | None = None,
    api_base_url: str | None = None,
    enable_local_bot_api: bool = True,
) -> Application:
    """
    Create and configure the Telegram bot application.
    
    Args:
        token: Bot token (defaults to config)
        api_base_url: Local Bot API server URL (defaults to config)
        enable_local_bot_api: Whether to use local Bot API server
        
    Returns:
        Configured Application instance
    """
    token = token or BOT_TOKEN

    # Setup logging
    setup_logging()

    # Build application
    builder = ApplicationBuilder().token(token)

    # Use local Bot API server for Rich Messages (Bot API 10.1+)
    if enable_local_bot_api and api_base_url:
        builder.base_url(api_base_url)
        logger.info("Using local Bot API server: %s", api_base_url)

    # Custom request for better timeout handling
    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=30.0,
        write_timeout=30.0,
        connect_timeout=10.0,
    )
    builder.request(request)

    app = builder.build()

    logger.info("Bot application created")
    return app


async def setup_bot(app: Application) -> None:
    """Setup bot commands and handlers after initialization."""
    from src.bot.handlers import register_handlers

    # Register all handlers
    register_handlers(app)

    # Set bot commands
    from telegram import BotCommand

    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("subscribe", "Subscribe to daily reports"),
        BotCommand("unsubscribe", "Unsubscribe from reports"),
        BotCommand("report", "Get latest analysis report"),
        BotCommand("status", "Check bot & database status"),
        BotCommand("indicators", "Technical indicators explained"),
        BotCommand("search", "Search symbol or company name"),
        BotCommand("help", "Show all commands"),
    ]

    await app.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


async def shutdown_bot(app: Application) -> None:
    """Graceful shutdown."""
    logger.info("Shutting down bot...")
    await app.shutdown()
