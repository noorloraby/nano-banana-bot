"""
Main entry point for running both Telegram bot and API server together.
Shares a single browser client instance between both services.
"""

import asyncio
import logging
import signal
import sys

import config
from browser_client import NanoBananaClient

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Shared browser client
browser_client = NanoBananaClient()


async def run_telegram_bot():
    """Run the Telegram bot."""
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
    
    # Import handlers from bot.py
    import bot
    
    # Replace bot's browser_client with shared one
    bot.browser_client = browser_client
    
    if not config.TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not set, skipping Telegram bot")
        return
    
    application = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler('start', bot.start_command))
    application.add_handler(CommandHandler('img', bot.img_command))
    application.add_handler(CallbackQueryHandler(bot.upscale_callback, pattern="^up:"))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, bot.handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE & ~filters.COMMAND, bot.handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.REPLY, bot.handle_text_reply))
    
    logger.info("Starting Telegram bot...")
    
    # Initialize and start polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keep running
    while True:
        await asyncio.sleep(3600)


async def run_api_server():
    """Run the FastAPI server."""
    import uvicorn
    
    # Import and configure API
    import api
    
    # Replace api's browser_client with shared one
    api.browser_client = browser_client
    
    # Remove the startup event since we're managing browser externally
    # We need to create a modified app or skip the startup
    
    logger.info(f"Starting API server on port {config.API_PORT}...")
    
    # Create uvicorn config
    uvicorn_config = uvicorn.Config(
        app="api:app",
        host="0.0.0.0",
        port=config.API_PORT,
        log_level="info",
        # Don't reload in production
        reload=False
    )
    
    server = uvicorn.Server(uvicorn_config)
    await server.serve()


async def main():
    """Main entry point - starts browser and both services."""
    logger.info("Starting Nano Banana (combined mode)...")
    
    # Start browser first
    try:
        await browser_client.start()
        logger.info("Browser initialized successfully")
    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        sys.exit(1)
    
    try:
        # Run both services concurrently
        await asyncio.gather(
            run_telegram_bot(),
            run_api_server()
        )
    except Exception as e:
        logger.error(f"Service error: {e}")
    finally:
        await browser_client.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
