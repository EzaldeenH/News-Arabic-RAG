"""
Telegram Bot Main Entry Point.
Arabic QA Bot - Middle East Focus
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from bot.app.handlers.message_handlers import router

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Main bot runner."""
    # Get bot token from environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment")
        return
    
    # Create bot with default properties
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    
    # Create dispatcher with memory storage for FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Include routers
    dp.include_router(router)
    
    # Bot startup handler
    @dp.startup()
    async def on_startup(bot: Bot):
        bot_user = await bot.get_me()
        logger.info(f"Bot started: @{bot_user.username}")
    
    # Bot shutdown handler
    @dp.shutdown()
    async def on_shutdown(bot: Bot):
        logger.info("Bot stopped")
        await storage.close()
    
    logger.info("Bot starting...")
    
    try:
        # Start polling
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        # Cleanup
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
