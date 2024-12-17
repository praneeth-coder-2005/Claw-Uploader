# main.py
import asyncio
import logging

from bot.handlers import bot
from bot.config import BOT_TOKEN

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

async def main():
    try:
        await bot.start(bot_token=BOT_TOKEN)
        await bot.run_until_disconnected()
    except Exception as e:
        logging.error(f"An error occurred in main: {e}")
    finally:
        await bot.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
