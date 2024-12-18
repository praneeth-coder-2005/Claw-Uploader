import asyncio
import logging

from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError

from bot.config import API_ID, API_HASH, BOT_TOKEN
from bot.handlers import url_processing, default_file_handler, rename_handler, cancel_handler, rename_process
from bot.services.progress_manager import ProgressManager
from bot.settings_handlers import settings_handler, set_thumbnail_handler, set_prefix_handler, add_rename_rule_handler, remove_rename_rule_handler, remove_rule_callback_handler, done_settings_handler, process_settings_input

# Initialize the bot
bot = TelegramClient('bot', API_ID, API_HASH)
progress_manager = ProgressManager()

# Handlers
async def start_handler(event):
    user = await event.get_sender()
    await event.respond(
        f"Hello {user.first_name}! 👋\n"
        f"I'm ready to upload files for you (up to 2GB).\n"
        f"Just send me a URL, and I'll handle the rest.\n\n"
        f"Available Commands:\n"
        f"/start - Start the bot\n"
        f"/help - Show this message\n"
        f"/settings - Change bot settings\n"
        f"/cancel - Cancel the current operation\n"
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
        f"/help - Show this message\n"
        f"/settings - Change bot settings\n"
        f"/cancel - Cancel the current operation"
    )


# Register handlers
def register_handlers(bot, progress_manager):
    bot.add_event_handler(start_handler, events.NewMessage(pattern='/start'))
    bot.add_event_handler(help_handler, events.NewMessage(pattern='/help'))
    bot.add_event_handler(
        lambda event: url_processing(event, progress_manager), events.NewMessage
    )
    bot.add_event_handler(
        lambda event: rename_process(event, progress_manager), events.NewMessage
    )
    bot.add_event_handler(
        lambda event: default_file_handler(event, progress_manager), events.CallbackQuery(data=lambda data: data.decode().startswith('default_'))
    )
    bot.add_event_handler(
        lambda event: rename_handler(event, progress_manager), events.CallbackQuery(data=lambda data: data.decode().startswith('rename_'))
    )
    bot.add_event_handler(
        lambda event: cancel_handler(event, progress_manager), events.CallbackQuery(data=lambda data: data.decode().startswith('cancel_'))
    )
    bot.add_event_handler(settings_handler, events.NewMessage(pattern='/settings'))
    bot.add_event_handler(set_thumbnail_handler, events.CallbackQuery(data=lambda data: data.decode() == 'set_thumbnail'))
    bot.add_event_handler(set_prefix_handler, events.CallbackQuery(data=lambda data: data.decode() == 'set_prefix'))
    bot.add_event_handler(add_rename_rule_handler, events.CallbackQuery(data=lambda data: data.decode() == 'add_rename_rule'))
    bot.add_event_handler(remove_rename_rule_handler, events.CallbackQuery(data=lambda data: data.decode() == 'remove_rename_rule'))
    bot.add_event_handler(remove_rule_callback_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('remove_rule_')))
    bot.add_event_handler(done_settings_handler, events.CallbackQuery(data=lambda data: data.decode() == 'done_settings'))
    bot.add_event_handler(process_settings_input, events.NewMessage)


async def main():
    register_handlers(bot, progress_manager) # Register handlers
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot has started successfully and is now running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)
    asyncio.run(main())
