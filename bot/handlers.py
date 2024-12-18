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
from bot.utils import get_file_name_extension, extract_filename_from_content_disposition
from bot.progress import ProgressBar
from bot.upload_downloader import download_and_upload

async def url_processing(event, progress_manager):
    try:
        url = event.text.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return

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
                logging.info(f"URL Processing - New task ID: {task_id}")
                task_data = {
                    "task_id": task_id,
                    "file_name": file_name,
                    "file_extension": file_extension,
                    "file_size": file_size,
                    "url": url,
                    "mime_type": mime_type,
                    "cancel_flag": False,
                    "message_id": None
                }
                
                progress_manager.add_task(task_id, task_data)

                logging.info(f"URL Processing - Task data stored: {progress_manager.progress_messages}")
                buttons = [[Button.inline("Default", data=f"default_{task_id}"),
                            Button.inline("Rename", data=f"rename_{task_id}")]]

                message = await event.respond(
                    f"Original File Name: {file_name}{file_extension}\nFile Size: {file_size / (1024 * 1024):.2f} MB\n\nChoose an option:",
                    buttons=buttons
                )

                task_data["message_id"] = message.id
                progress_manager.update_task(task_id,task_data)

    except aiohttp.ClientError as e:
        logging.error(f"AIOHTTP Error fetching URL {url}: {e}, url: {url}")
        await event.respond(f"Error fetching URL: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while processing URL {url}: {e}, url: {url}")
        await event.respond(f"An error occurred: {e}")

async def default_file_handler(event, progress_manager):
    task_id = event.data.decode().split('_')[1]
    user_id = event.sender_id  # Get user_id before checking task_data

    logging.info(f"Default File Handler - Task ID: {task_id}")
    logging.info(f"Default File Handler - Current tasks: {progress_manager.progress_messages}")

    task_data = progress_manager.get_task(task_id)

    if task_data:
        # Download and upload in the background
        asyncio.create_task(download_and_upload_in_background(event, task_data, user_id, progress_manager))
    else:
        await event.answer("No Active Download")

async def download_and_upload_in_background(event, task_data, user_id, progress_manager):
    try:
        file_name = task_data["file_name"]
        file_extension = task_data["file_extension"]
        file_size = task_data["file_size"]
        url = task_data["url"]
        task_id = task_data["task_id"]

        # Prepend the default prefix
        file_name = f"{DEFAULT_PREFIX}{file_name}{file_extension}"

        message_id = task_data.get("message_id")
        message = await event.client.get_messages(event.chat_id, ids=message_id)

        if not message:
            logging.error(f"Could not retrieve message with ID: {message_id}")
            await event.respond("Error: Could not find the original message to update.")
            return

        progress_bar = ProgressBar(file_size, "Processing", event.client, event, task_id, file_name, file_size)
        task_data["progress_bar"] = progress_bar
        progress_manager.update_task(task_id, task_data)

        await download_and_upload(event, url, file_name, file_size, task_data["mime_type"], task_id, file_extension, event, user_id, progress_manager)

    except Exception as e:
        logging.error(f"Error in background download and upload: {e}")
        await event.respond(f"An error occurred during the download and upload process.")

    finally:
        progress_manager.remove_task(task_id)

async def rename_handler(event, progress_manager):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = progress_manager.get_task(task_id)
        if task_data:
            progress_manager.update_task_status(task_id,"rename_requested")
            await event.answer(message='Send your desired file name (without extension):')
        else:
            await event.answer("No Active Download")
    except Exception as e:
        logging.error(f"Error in rename_handler: {e}")
        await event.respond(f"An error occurred. Please try again later.")

async def cancel_handler(event, progress_manager):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = progress_manager.get_task(task_id)
        if task_data:
            progress_manager.set_cancel_flag(task_id, True)
            progress_bar = task_data.get("progress_bar")
            if progress_bar:
                await progress_bar.stop("Cancelled by User")
            else:
                logging.warning(f"No progress bar found for task_id: {task_id}")
            await event.answer("Upload Canceled")
        else:
            await event.answer("No active download to cancel.")
    except Exception as e:
        logging.error(f"Error in cancel_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

async def rename_process(event, progress_manager):
    try:
        user_id = event.sender_id
        task_id, task_data = progress_manager.get_task_by_status("rename_requested")


        if not task_id:
            return

        if task_data and task_data.get("status") == "rename_requested" and event.sender_id == user_id:
            new_file_name = event.text.strip()
            file_extension = task_data["file_extension"]
            file_size = task_data["file_size"]
            url = task_data["url"]
            await event.delete()

            # Prepend default prefix to the new file name
            new_file_name = f"{DEFAULT_PREFIX}{new_file_name}{file_extension}"

            message = await event.respond(f"Your new file name is: {new_file_name}")
            task_data["message_id"] = message.id
            task_data["status"] = "default"
            task_data["file_name"] = new_file_name  # Update the file_name in task_data
            progress_manager.update_task(task_id,task_data)
            asyncio.create_task(download_and_upload_in_background(event, task_data, user_id, progress_manager))
        else:
            await event.respond("No active rename request found.")
    except Exception as e:
        logging.error(f"Error in rename_process: {e}")
        await event.respond(f"An error occurred. Please try again later")
