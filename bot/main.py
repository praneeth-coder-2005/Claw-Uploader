import asyncio
import logging

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from bot.config import API_ID, API_HASH, BOT_TOKEN
from bot.handlers import url_processing, default_file_handler, rename_handler, cancel_handler, rename_process

# Initialize the bot
bot = TelegramClient('bot', API_ID, API_HASH)

# Handlers
async def start_handler(event):
    user = await event.get_sender()
    await event.respond(
        f"👋 Hello {user.first_name}! I'm a URL Uploader bot.\n\n"
        f"**Here's what I can do:**\n\n"
        f"1. Send me a direct download URL, and I'll upload it to Telegram.\n"
        f"2. The maximum file size I can handle is 2GB.\n"
        f"3. You can choose to upload with the default filename or rename it.\n"
        f"4. You can cancel the upload at any time.\n\n"
        f"**Commands:**\n"
        f"/start - Start the bot\n"
        f"/help - Show this help message\n"
        f"/cancel - Cancel the current operation\n\n"
        f"Just send me a URL to get started!"
    )

async def help_handler(event):
    await event.respond(
        "**Here's how to use this bot:**\n\n"
        "1. Send me a direct download URL (max 2GB).\n"
        "2. Choose **Default** to upload with the original filename.\n"
        "3. Choose **Rename** to give the file a custom name.\n"
        "4. You can use the /cancel command to stop the process.\n\n"
        "**Available Commands:**\n"
        f"/start - Start the bot\n"
        f"/help - Show this help message\n"
        f"/cancel - Cancel the current operation\n"
    )

# Register handlers
def register_handlers(bot):
    bot.add_event_handler(start_handler, events.NewMessage(pattern='/start'))
    bot.add_event_handler(help_handler, events.NewMessage(pattern='/help'))
    bot.add_event_handler(url_processing, events.NewMessage)
    bot.add_event_handler(rename_process, events.NewMessage)
    bot.add_event_handler(default_file_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('default_')))
    bot.add_event_handler(rename_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('rename_')))
    bot.add_event_handler(cancel_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('cancel_')))

async def main():
    register_handlers(bot)
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot has started successfully and is now running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)
    asyncio.run(main())
