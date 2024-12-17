# handlers/__init__.py
from telethon import TelegramClient, events
from .commands import start_handler, help_handler, settings_handler
from .callbacks import set_thumbnail_handler, set_prefix_handler, add_rename_rule_handler, remove_rename_rule_handler, remove_rule_callback_handler, done_settings_handler, default_file_handler, rename_handler, cancel_handler, download_and_upload, upload_thumb
from .messages import url_processing, rename_process
from .settings import handle_settings_input
from bot.config import API_ID, API_HASH

bot = TelegramClient('bot', API_ID, API_HASH)

# Register all handlers
def register_handlers(bot):
    bot.add_event_handler(start_handler, events.NewMessage(pattern='/start'))
    bot.add_event_handler(help_handler, events.NewMessage(pattern='/help'))
    bot.add_event_handler(settings_handler, events.NewMessage(pattern='/settings'))
    bot.add_event_handler(handle_settings_input, events.NewMessage)
    bot.add_event_handler(set_thumbnail_handler, events.CallbackQuery(data=b"set_thumbnail"))
    bot.add_event_handler(set_prefix_handler, events.CallbackQuery(data=b"set_prefix"))
    bot.add_event_handler(add_rename_rule_handler, events.CallbackQuery(data=b"add_rename_rule"))
    bot.add_event_handler(remove_rename_rule_handler, events.CallbackQuery(data=b"remove_rename_rule"))
    bot.add_event_handler(remove_rule_callback_handler, events.CallbackQuery(data=lambda data: data.startswith(b"remove_rule_")))
    bot.add_event_handler(done_settings_handler, events.CallbackQuery(data=b"done_settings"))
    bot.add_event_handler(default_file_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('default_')))
    bot.add_event_handler(rename_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('rename_')))
    bot.add_event_handler(cancel_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('cancel_')))
    bot.add_event_handler(url_processing, events.NewMessage)
    bot.add_event_handler(rename_process, events.NewMessage)

# Register handlers
register_handlers(bot)
