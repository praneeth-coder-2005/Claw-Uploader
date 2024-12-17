# bot/handlers.py

import aiohttp
import asyncio
import logging
import os
import uuid
import time
import math
import magic

from telethon import events, Button, types
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedDocument, DocumentAttributeFilename
from telethon.errors import FloodWaitError

from bot.config import DEFAULT_PREFIX, MAX_FILE_SIZE, MAX_RETRIES, RETRY_DELAY, CHUNK_SIZE, MAX_FILE_PARTS
from bot.utils import get_user_settings, upload_thumb, get_file_name_extension, extract_filename_from_content_disposition
from bot.services.progress_manager import ProgressManager
from bot.progress import ProgressBar
from bot.upload_downloader import download_and_upload

# Initialize ProgressManager
progress_manager = ProgressManager()

async def url_processing(event):
    try:
        url = event.text.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return  # Ignore non-URL messages

        await event.delete()
        user_id = event.sender_id
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

async def rename_process(event):
    try:
        task_id, task_data = progress_manager.get_task_by_status("rename_requested")
        user_id = event.sender_id
        if task_id and event.sender_id == user_id:
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
