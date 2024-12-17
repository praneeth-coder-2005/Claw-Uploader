# handlers/__init__.py
from telethon import TelegramClient, events
from .commands import start_handler, help_handler, settings_handler
from .callbacks import set_thumbnail_handler, set_prefix_handler, add_rename_rule_handler, remove_rename_rule_handler, remove_rule_callback_handler, done_settings_handler, default_file_handler, rename_handler, cancel_handler
from .messages import url_processing, rename_process
from .settings import handle_settings_input
from bot.config import API_ID, API_HASH
import asyncio
import aiohttp
import logging
import os
import time
import uuid
import math
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
from bot.services.progress import ProgressManager

# Initialize ProgressManager
progress_manager = ProgressManager()

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

# Constants
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB now
CHUNK_SIZE = 2 * 1024 * 1024 # 2 MB initial chunk size
MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_FILE_PARTS = 3000

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
                            mime_type=mime_type,
                            attributes=[DocumentAttributeFilename(file_name)],
                            thumb=types.InputFile(id=thumb_id, parts=1, name="thumb.jpg", md5_checksum="")
                        )
                    else:
                        media = InputMediaUploadedDocument(
                            file=file,
                            mime_type=mime_type,
                            attributes=[DocumentAttributeFilename(file_name)]
                        )
                    
                    await bot(SendMediaRequest(
                        peer=await bot.get_input_entity(current_event.chat_id),
                        media=media,
                        message=f"File Name: {file_name}{file_extension}",
                    ))
                    await progress_bar.stop("Upload Complete")
                except FloodWaitError as e:
                    logging.warning(f"Flood wait error during upload: {e}")
                    await asyncio.sleep(e.seconds)
                    await download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension, current_event, user_id)
                    return
                except Exception as e:
                      logging.error(f"An error occurred during upload: {e}, url: {url}")
                      await current_event.respond(f"An error occurred during upload: {e}")
                      return

        else:
             await current_event.respond(
                f"Error: Download incomplete (Size mismatch) file_size is: {file_size} and downloaded size is: {downloaded_size}")

    except Exception as e:
        logging.error(f"An unexpected error occurred in downlaod_and_upload: {e}, url: {url}")
        await current_event.respond(f"An error occurred: {e}")
    finally:
       progress_manager.remove_task(task_id)
       if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
