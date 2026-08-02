"""
telegram/menu — menu button (≡) configuration.
"""
from __future__ import annotations

from telegram import MenuButtonCommands

from marketmeter.core.logging import get_logger

logger = get_logger(__name__)


async def _setup_menu_button(app):
    """Configure the menu button (≡) with commands list."""
    logger.info("Setting up menu button (≡)...")
    try:
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Menu button (≡) configured successfully")
    except Exception as e:
        logger.warning("Failed to set menu button: %s", e)
    logger.info("Menu button setup complete")


async def _setup_menu_button_post_start(app):
    """Fallback: configure menu button after start if post_init didn't run."""
    try:
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Menu button (≡) configured (post_start)")
    except Exception as e:
        logger.warning("Failed to set menu button (post_start): %s", e)


__all__ = ["_setup_menu_button", "_setup_menu_button_post_start"]