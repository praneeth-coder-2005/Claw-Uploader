# handlers.py
import asyncio
import logging
import os
import time
import uuid
import math
import aiohttp
import magic
from telethon import TelegramClient, events, Button, types
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedDocument, DocumentAttributeFilename, InputMediaUploadedPhoto
from telethon.utils import get_display_name
from telethon.errors import FloodWaitError
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest

from bot.utils import get_file_name_extension, extract_filename_from_content_disposition, load_settings, save_settings, get_user_settings, set_user_setting
from bot.progress import ProgressBar
from bot.config import BOT_TOKEN, API_ID, API_HASH, DEFAULT_THUMBNAIL, DEFAULT_PREFIX

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

# Constants
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB now
CHUNK_SIZE = 2 * 1024 * 1024 # 2 MB initial chunk size
MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_FILE_PARTS = 3000

# Global Class for progress messages
class ProgressManager:
    def __init__(self):
        self.progress_messages = {}

    def add_task(self, task_id, data):
        self.progress_messages[task_id] = data

    def get_task(self, task_id):
        return self.progress_messages.get(task_id)

    def remove_task(self, task_id):
        if task_id in self.progress_messages:
            del self.progress_messages[task_id]

    def update_task_status(self, task_id, status):
        if task_id in self.progress_messages:
            self.progress_messages[task_id]["status"] = status

    def get_task_by_status(self, status):
        for task_id, data in self.progress_messages.items():
            if "status" in data and data["status"] == status:
                return task_id, data
        return None, None

    def get_cancel_flag(self, task_id):
        task = self.get_task(task_id)
        if task:
            return task.get("cancel_flag", False)
        return False

    def set_cancel_flag(self, task_id, value):
        task = self.get_task(task_id)
        if task:
            task["cancel_flag"] = value

    def set_message_id(self, task_id, message_id):
        task = self.get_task(task_id)
        if task:
            task["message_id"] = message_id

# Initialize ProgressManager
progress_manager = ProgressManager()

# Main Bot Logic
bot = TelegramClient('bot', API_ID, API_HASH)

@bot.on(events.NewMessage(pattern='/start'))
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

@bot.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    try:
        await event.respond('Available Commands:\n/start - Start the bot\n/help - Show this message\n/settings - Configure custom settings')
    except Exception as e:
        logging.error(f"Error in /help handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.NewMessage(pattern='/settings'))
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

@bot.on(events.CallbackQuery(data=b"set_thumbnail"))
async def set_thumbnail_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "set_thumbnail")
    await event.respond("Please send me the thumbnail URL:")

@bot.on(events.CallbackQuery(data=b"set_prefix"))
async def set_prefix_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "set_prefix")
    await event.respond("Please send me the new prefix:")

@bot.on(events.CallbackQuery(data=b"add_rename_rule"))
async def add_rename_rule_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "add_rename_rule")
    await event.respond("Please send me the text to remove from filenames:")

@bot.on(events.CallbackQuery(data=b"remove_rename_rule"))
async def remove_rename_rule_handler(event):
    user_id = event.sender_id
    user_settings = get_user_settings(user_id)
    if user_settings["rename_rules"]:
        progress_manager.update_task_status(user_id, "remove_rename_rule")
        buttons = [
            [Button.inline(rule, data=f"remove_rule_{i}")]
            for i, rule in enumerate(user_settings["rename_rules"])
        ]
        await event.respond("Which rule do you want to remove?", buttons=buttons)
    else:
        await event.answer("You don't have any rename rules set.")

@bot.on(events.CallbackQuery(data=lambda data: data.startswith(b"remove_rule_")))
async def remove_rule_callback_handler(event):
    user_id = event.sender_id
    rule_index = int(event.data.decode().split("_")[-1])
    user_settings = get_user_settings(user_id)
    if 0 <= rule_index < len(user_settings["rename_rules"]):
        removed_rule = user_settings["rename_rules"].pop(rule_index)
        set_user_setting(user_id, "rename_rules", user_settings["rename_rules"])
        await event.answer(f"Removed rule: {removed_rule}")
        await settings_handler(event)  # Refresh the settings message
    else:
        await event.answer("Invalid rule index.")

@bot.on(events.CallbackQuery(data=b"done_settings"))
async def done_settings_handler(event):
    await event.answer("Settings saved!")
    await event.delete()

@bot.on(events.NewMessage)
async def handle_settings_input(event):
    user_id = event.sender_id
    status = progress_manager.get_task(user_id)
    
    if status:
        if status["status"] == "set_thumbnail":
            thumbnail_url = event.text.strip()
            set_user_setting(user_id, "thumbnail", thumbnail_url)
            await event.respond(f"Thumbnail set to: {thumbnail_url}")
            progress_manager.remove_task(user_id)
        
        elif status["status"] == "set_prefix":
             new_prefix = event.text.strip()
             set_user_setting(user_id, "prefix", new_prefix)
             await event.respond(f"Prefix set to: {new_prefix}")
             progress_manager.remove_task(user_id)
        
        elif status["status"] == "add_rename_rule":
            new_rule = event.text.strip()
            user_settings = get_user_settings(user_id)
            user_settings["rename_rules"].append(new_rule)
            set_user_setting(user_id, "rename_rules", user_settings["rename_rules"])
            await event.respond(f"Added rename rule: {new_rule}")
            progress_manager.remove_task(user_id)

    else:
        await url_processing(event)

async def upload_thumb(event, file_path, user_id):
    try:
        user_settings = get_user_settings(user_id)
        thumbnail_url = user_settings.get("thumbnail", DEFAULT_THUMBNAIL)

        # Download the thumbnail
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url) as thumb_response:
                if thumb_response.status == 200:
                    thumb_data = await thumb_response.read()
                    # Upload thumbnail as a photo
                    file = await bot.upload_file(thumb_data, file_name="thumbnail.jpg")
                    # Get photo ID
                    photo = await bot(
                        SendMediaRequest(
                            peer=await bot.get_input_entity(event.chat_id),
                            media=InputMediaUploadedPhoto(file=file),
                            message="Uploading Thumbnail"
                        )
                    )
                    return photo.photo.id
                else:
                    logging.error(f"Error downloading thumbnail from {thumbnail_url}: Status {thumb_response.status}")
                    return None

    except Exception as e:
        logging.error(f"Error uploading thumbnail: {e}")
        return None

@bot.on(events.NewMessage)
async def url_processing(event):
    try:
        url = event.text.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return  # Ignore non-URL messages

        await event.delete()
        user_id = event.sender_id
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True, timeout=10) as response:
                    response.raise_for_status()
                    file_size = int(response.headers.get('Content-Length', 0))

                    if file_size > MAX_FILE_SIZE:
                        await event.respond('File size exceeds the limit of 2GB.')
                        return

                    mime_type = response.headers.get('Content-Type', "application/octet-stream")
                    content_disposition = response.headers.get('Content-Disposition')

                    original_file_name = extract_filename_from_content_disposition(content_disposition)
                    if not original_file_name:
                        file_name, file_extension = get_file_name_extension(url)
                    else:
                        file_name, file_extension = os.path.splitext(original_file_name)
                        
                    task_id = str(uuid.uuid4())
                    task_data = {
                        "file_name": file_name,
                        "file_extension": file_extension,
                        "file_size": file_size,
                        "url": url,
                        "mime_type": mime_type,
                         "cancel_flag": False
                    }
                    progress_manager.add_task(task_id, task_data)
                    buttons = [[Button.inline("Default", data=f"default_{task_id}"),
                                Button.inline("Rename", data=f"rename_{task_id}")]]
                    await event.respond(
                        f"Original File Name: {file_name}{file_extension}\nFile Size: {file_size / (1024 * 1024):.2f} MB",
                        buttons=buttons)

        except aiohttp.ClientError as e:
            logging.error(f"AIOHTTP Error fetching URL {url}: {e}, url: {url}")
            await event.respond(f"Error fetching URL: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while processing URL {url}: {e}, url: {url}")
            await event.respond(f"An error occurred: {e}")
    except Exception as e:
        logging.error(f"Error in url_processing handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.CallbackQuery(data=lambda data: data.decode().startswith('default_')))
async def default_file_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = progress_manager.get_task(task_id)
        user_id = event.sender_id
        if task_data:
            user_settings = get_user_settings(user_id)
            user_prefix = user_settings.get("prefix", DEFAULT_PREFIX)

            file_name = task_data["file_name"]
            file_extension = task_data["file_extension"]
            file_size = task_data["file_size"]
            url = task_data["url"]
            mime_type = task_data["mime_type"]

            # Apply rename rules
            for rule in user_settings["rename_rules"]:
                file_name = file_name.replace(rule, "")
            
            message = await event.respond(message="Processing file upload..")
            progress_manager.set_message_id(task_id, message.id)

            await download_and_upload(event, url, f"{user_prefix}{file_name}{file_extension}", file_size, mime_type, task_id, file_extension, event, user_id)
        else:
             await event.answer("No Active Download")
    except Exception as e:
        logging.error(f"Error in default_file_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.CallbackQuery(data=lambda data: data.decode().startswith('rename_')))
async def rename_handler(event):
    try:
         task_id = event.data.decode().split('_')[1]
         if progress_manager.get_task(task_id):
            progress_manager.update_task_status(task_id, "rename_requested")
            await event.answer(message='Send your desired file name:')
         else:
            await event.answer("No Active Download")

    except Exception as e:
        logging.error(f"Error in rename_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.NewMessage)
async def rename_process(event):
    try:
       task_id, task_data = progress_manager.get_task_by_status("rename_requested")
       user_id = event.sender_id
       if task_id and event.sender_id == event.sender_id:
            user_settings = get_user_settings(user_id)
            user_prefix = user_settings.get("prefix", DEFAULT_PREFIX)

            new_file_name = event.text
            file_extension = task_data["file_extension"]
            file_size = task_data["file_size"]
            url = task_data["url"]
            mime_type = task_data["mime_type"]
            await event.delete()
            message = await event.respond(f"Your new File name is: {user_prefix}{new_file_name}{file_extension}")
            progress_manager.set_message_id(task_id, message.id)
            await download_and_upload(event, url, f"{user_prefix}{new_file_name}{file_extension}", file_size, mime_type, task_id, file_extension, event, user_id)
            return
    except Exception as e:
        logging.error(f"Error in rename_process: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.CallbackQuery(data=lambda data: data.decode().startswith('cancel_')))
async def cancel_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = progress_manager.get_task(task_id)
        if task_data:
            progress_manager.set_cancel_flag(task_id, True)
            await task_data["progress_bar"].stop("Canceled by User")
            progress_manager.remove_task(task_id)
            await event.answer("Upload Canceled")
        else:
            await event.answer("No active download to cancel.")
    except Exception as e:
        logging.error(f"Error in cancel_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

async def download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension, current_event, user_id):
    temp_file_path = f"temp_{task_id}"
    try:
        downloaded_size = 0
        start_time = time.time()
        download_speed = 0
        upload_speed = 0

        task_data = progress_manager.get_task(task_id)
        message_id = task_data.get("message_id")
        progress_bar = ProgressBar(file_size, "Processing", bot, current_event, task_id, file_name, file_size)
        if message_id:
            progress_bar.set_message_id(message_id)
        task_data["progress_bar"] = progress_bar
        
        for attempt in range(MAX_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
                     async with session.get(url, timeout=None) as response:
                        response.raise_for_status()
                        
                        with open(temp_file_path, "wb") as temp_file:
                            while True:
                                if progress_manager.get_cancel_flag(task_id):
                                    return
                                
                                chunk = await response.content.readany()
                                if not chunk:
                                    break

                                temp_file.write(chunk)
                                downloaded_size += len(chunk)
                                elapsed_time = time.time() - start_time
                                if elapsed_time > 0:
                                    download_speed = downloaded_size / elapsed_time
                                await progress_bar.update_progress(downloaded_size / file_size, download_speed=download_speed)
                        break
            except aiohttp.ClientError as e:
                logging.error(f"Download error (attempt {attempt + 1}/{MAX_RETRIES}) from {url}: {e}, url:{url}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logging.error(f"Maximum retries reached for download from {url}, url: {url}")
                    await current_event.respond(f"Download Error: {e}. Maximum retries reached.")
                    return
            except Exception as e:
                logging.error(f"An exception occurred in downlaod_and_upload while downloading file : {e}, url: {url}")
                await current_event.respond(f"An error occurred : {e}")
                return
        if downloaded_size == file_size:
            start_upload_time = time.time()
            with open(temp_file_path, "rb") as f:
                mime = magic.Magic(mime=True)
                mime_type = mime.from_file(temp_file_path)

                # Calculate number of parts
                parts = math.ceil(file_size / CHUNK_SIZE)

                upload_chunk_size = CHUNK_SIZE
                if parts > MAX_FILE_PARTS:
                    upload_chunk_size = math.ceil(file_size / MAX_FILE_PARTS)
                    logging.warning(f"Reducing upload chunk size to {upload_chunk_size / (1024*1024):.2f} MB due to excessive parts {parts}")
                
                thumb_id = await upload_thumb(event, temp_file_path, user_id)

                file = await bot.upload_file(
                    f,
                    file_name=file_name,
                     progress_callback=lambda current, total: asyncio.create_task(
                            progress_bar.update_progress(current / total))
                    )
                uploaded_size = 0
                elapsed_upload_time = time.time() - start_upload_time
                upload_speed = file_size / elapsed_upload_time if elapsed_upload_time > 0 else 0
                await progress_bar.update_progress(1, download_speed=download_speed, upload_speed=upload_speed)
                try:
                    # Send with thumbnail
                    if thumb_id:
                        media = InputMediaUploadedDocument(
                            file=file,
                        
