# main.py
import asyncio
import logging

from bot.handlers import bot, register_handlers  # Import bot and register_handlers
from bot.config import BOT_TOKEN

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

async def main():
    try:
        register_handlers(bot)  # Register handlers here
        await bot.start(bot_token=BOT_TOKEN)
        await bot.run_until_disconnected()
    except Exception as e:
        logging.error(f"An error occurred in main: {e}")
    finally:
        await bot.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
