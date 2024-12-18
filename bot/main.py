import asyncio
import logging

from telethon import TelegramClient, events, Button, types
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedDocument, DocumentAttributeFilename, InputMediaUploadedPhoto
from telethon.errors import FloodWaitError

from bot.config import API_ID, API_HASH, BOT_TOKEN, DEFAULT_PREFIX, DEFAULT_THUMBNAIL
from bot.utils import get_user_settings, set_user_setting, upload_thumb, get_file_name_extension, extract_filename_from_content_disposition
from bot.handlers import url_processing, default_file_handler, rename_handler, cancel_handler, rename_process
from bot.handlers import set_thumbnail_handler, set_prefix_handler, add_rename_rule_handler, remove_rename_rule_handler, remove_rule_callback_handler, done_settings_handler

# Initialize the bot
bot = TelegramClient('bot', API_ID, API_HASH)

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
        f"/settings - Configure custom settings")

async def help_handler(event):
    await event.respond(
        'Available Commands:\n/start - Start the bot\n/help - Show this message\n/settings - Configure custom settings')

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
        [Button.inline("✅ Done", data="done_settings")]]
    await event.respond(message, buttons=buttons)

async def handle_settings_input(event):
    user_id = event.sender_id
    task_data = getattr(event.client, 'task_data', {}).get(str(user_id))

    if task_data:
        status = task_data.get("status")
        if status == "set_thumbnail":
            if event.media:
                try:
                    # Download and process the thumbnail sent by the user
                    thumb_file = await event.client.download_media(event.media, file="bot/")
                    file = await event.client.upload_file(thumb_file, file_name="thumbnail.jpg")
                    photo = await event.client(SendMediaRequest(peer=await event.client.get_input_entity(event.chat_id),media=InputMediaUploadedPhoto(file=file),message="Thumbnail set!"))
                    file_id = photo.photo.id
                    set_user_setting(user_id, "thumbnail", file_id)
                    await event.respond("Thumbnail updated!")
                    os.remove(thumb_file)  # Clean up
                except Exception as e:
                    logging.error(f"Error setting thumbnail: {e}")
                    await event.respond("Error setting thumbnail. Please try again.")
            else:
                await event.respond("Please send me an image to use as a thumbnail.")
            if str(user_id) in event.client.task_data:
                del event.client.task_data[str(user_id)]

        elif status == "set_prefix":
            # Set the new prefix
            new_prefix = event.text.strip()
            set_user_setting(user_id, "prefix", new_prefix)
            await event.respond(f"Prefix set to: {new_prefix}")
            if str(user_id) in event.client.task_data:
                del event.client.task_data[str(user_id)]

        elif status == "add_rename_rule":
            # Add a new rename rule
            new_rule = event.text.strip()
            user_settings = get_user_settings(user_id)
            user_settings["rename_rules"].append(new_rule)
            set_user_setting(user_id, "rename_rules", user_settings["rename_rules"])
            await event.respond(f"Added rename rule: {new_rule}")
            if str(user_id) in event.client.task_data:
                del event.client.task_data[str(user_id)]

# Register handlers
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
    bot.add_event_handler(url_processing, events.NewMessage)
    bot.add_event_handler(rename_process, events.NewMessage)
    bot.add_event_handler(default_file_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('default_')))
    bot.add_event_handler(rename_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('rename_')))
    bot.add_event_handler(cancel_handler, events.CallbackQuery(data=lambda data: data.decode().startswith('cancel_')))

async def main():
    register_handlers(bot) # Register handlers
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)
    asyncio.run(main())
