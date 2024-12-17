# bot/handlers/commands.py
import logging
from telethon import events, Button
from telethon.utils import get_display_name
from bot.utils import get_user_settings

async def start_handler(event):
    try:
        user = await event.get_sender()
        message_text = (f"Hello {get_display_name(user)}! 👋\n"
                        "I'm ready to upload files for you. I will upload up to 2GB.\n"
                        "Just send me a URL, and I'll handle the rest.\n\n"
                        "Available Commands:\n"
                        "/start - Start the bot\n"
                        "/help - Show this message\n"
                        "/settings - Configure custom settings")
        await event.respond(message_text)
    except Exception as e:
        logging.error(f"Error in /start handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

async def help_handler(event):
    try:
        await event.respond('Available Commands:\n/start - Start the bot\n/help - Show this message\n/settings - Configure custom settings')
    except Exception as e:
        logging.error(f"Error in /help handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

async def settings_handler(event):
    user_id = event.sender_id
    user_settings = get_user_settings(user_id)

    message = (
        "Current Settings:\n\n"
        f"🖼️ **Thumbnail:** {user_settings['thumbnail'] if user_settings['thumbnail'] else 'Default'}\n"
        f"✍️ **Prefix:** {user_settings['prefix'] if user_settings['prefix'] else 'Default'}\n"
        f"✏️ **Rename Rules:** {', '.join(user_settings['rename_rules']) if user_settings['rename_rules'] else 'None'}\n\n"
        "What do you want to change?"
    )
    
    buttons = [
        [Button.inline("🖼️ Set Thumbnail", data="set_thumbnail")],
        [Button.inline("✍️ Set Prefix", data="set_prefix")],
        [Button.inline("✏️ Add Rename Rule", data="add_rename_rule")],
        [Button.inline("❌ Remove Rename Rule", data="remove_rename_rule")],
        [Button.inline("✅ Done", data="done_settings")],
    ]

    await event.respond(message, buttons=buttons)
