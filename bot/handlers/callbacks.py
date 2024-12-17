# bot/handlers/callbacks.py
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
from bot.utils import get_file_name_extension, extract_filename_from_content_disposition, load_settings, save_settings, get_user_settings, set_user_setting, upload_thumb
from bot.progress import ProgressBar
from bot.config import BOT_TOKEN, API_ID, API_HASH, DEFAULT_THUMBNAIL, DEFAULT_PREFIX
from bot.services.progress import ProgressManager

import asyncio

progress_manager = ProgressManager()

async def set_thumbnail_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "set_thumbnail")
    await event.respond("Please send me the image to use as a thumbnail:")

async def set_prefix_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "set_prefix")
    await event.respond("Please send me the new prefix:")

async def add_rename_rule_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "add_rename_rule")
    await event.respond("Please send me the text to remove from filenames:")

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

async def remove_rule_callback_handler(event):
    user_id = event.sender_id
    rule_index = int(event.data.decode().split("_")[-1])
    user_settings = get_user_settings(user_id)
    if 0 <= rule_index < len(user_settings["rename_rules"]):
        removed_rule = user_settings["rename_rules"].pop(rule_index)
        set_user_setting(user_id, "rename_rules", user_settings["rename_rules"])
        await event.answer(f"Removed rule: {removed_rule}")
        await settings_handler(event)
    else:
        await event.answer("Invalid rule index.")

async def done_settings_handler(event):
    await event.answer("Settings saved!")
    await event.delete()

async def default_file_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
        user_id = event.sender_id  # Get user_id before checking task_data

        task_data = progress_manager.get_task(task_id)

        if task_data:  # Correctly check if task_data exists
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

# Constants
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB now
CHUNK_SIZE = 2 * 1024 * 1024 # 2 MB initial chunk size
MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_FILE_PARTS = 3000

async def download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension, current_event, user_id):
    temp_file_path = f"temp_{task_id}"
    try:
        downloaded_size = 0
        start_time = time.time()
        download_speed = 0
        upload_speed = 0

        task_data = progress_manager.get_task(task_id)
        message_id = task_data.get("message_id")
        progress_bar = ProgressBar(file_size, "Processing", event.client, current_event, task_id, file_name, file_size)
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

                file = await event.client.upload_file(
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
                    
                    await event.client(SendMediaRequest(
                        peer=await event.client.get_input_entity(current_event.chat_id),
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
