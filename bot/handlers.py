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
from bot.progress import ProgressBar
from bot.upload_downloader import download_and_upload

async def url_processing(event):
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

                event.client.task_data = {task_id: task_data}

                logging.info(f"URL Processing - Task data stored: {event.client.task_data}")
                buttons = [[Button.inline("Default", data=f"default_{task_id}"),
                            Button.inline("Rename", data=f"rename_{task_id}")]]

                message = await event.respond(
                    f"Original File Name: {file_name}{file_extension}\nFile Size: {file_size / (1024 * 1024):.2f} MB",
                    buttons=buttons
                )

                task_data["message_id"] = message.id
                event.client.task_data[task_id] = task_data

    except aiohttp.ClientError as e:
        logging.error(f"AIOHTTP Error fetching URL {url}: {e}, url: {url}")
        await event.respond(f"Error fetching URL: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while processing URL {url}: {e}, url: {url}")
        await event.respond(f"An error occurred: {e}")

async def default_file_handler(event):
    task_id = event.data.decode().split('_')[1]
    user_id = event.sender_id

    logging.info(f"Default File Handler - Task ID: {task_id}")
    logging.info(f"Default File Handler - Current tasks: {event.client.task_data}")

    task_data = event.client.task_data.get(task_id)

    if task_data:
        asyncio.create_task(download_and_upload_in_background(event, task_data, user_id))
    else:
        await event.answer("No Active Download")

async def download_and_upload_in_background(event, task_data, user_id):
    try:
        user_settings = get_user_settings(user_id)
        user_prefix = user_settings.get("prefix", DEFAULT_PREFIX)

        file_name = task_data["file_name"]
        file_extension = task_data["file_extension"]
        file_size = task_data["file_size"]
        url = task_data["url"]
        mime_type = task_data["mime_type"]
        task_id = task_data["task_id"]

        for rule in user_settings["rename_rules"]:
            file_name = file_name.replace(rule, "")

        file_name = f"{user_prefix}{file_name}{file_extension}"

        message_id = task_data.get("message_id")
        message = await event.client.get_messages(event.chat_id, ids=message_id)

        if not message:
            logging.error(f"Could not retrieve message with ID: {message_id}")
            await event.respond("Error: Could not find the original message to update.")
            return

        progress_bar = ProgressBar(file_size, "Processing", event.client, event, task_id, file_name, file_size)
        task_data["progress_bar"] = progress_bar
        event.client.task_data[task_id] = task_data

        await download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension, event, user_id)

    except Exception as e:
        logging.error(f"Error in background download and upload: {e}")
        await event.respond(f"An error occurred during the download and upload process.")

    finally:
        if task_id in event.client.task_data:
            del event.client.task_data[task_id]

async def rename_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = event.client.task_data.get(task_id)
        if task_data:
            task_data["status"] = "rename_requested"
            event.client.task_data[task_id] = task_data
            await event.answer(message='Send your desired file name:')
        else:
            await event.answer("No Active Download")
    except Exception as e:
        logging.error(f"Error in rename_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

async def cancel_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = event.client.task_data.get(task_id)
        if task_data:
            task_data["cancel_flag"] = True
            event.client.task_data[task_id] = task_data
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

async def rename_process(event):
    try:
        user_id = event.sender_id
        task_id = None
        for key, task in event.client.task_data.items():
            if task.get("status") == "rename_requested" and event.sender_id == user_id:
                task_id = key
                break

        if not task_id:
            return

        task_data = event.client.task_data.get(task_id)
        if task_data and task_data.get("status") == "rename_requested":
            user_settings = get_user_settings(user_id)
            user_prefix = user_settings.get("prefix", DEFAULT_PREFIX)

            new_file_name = event.text.strip()
            file_extension = task_data["file_extension"]
            file_size = task_data["file_size"]
            url = task_data["url"]
            mime_type = task_data["mime_type"]
            await event.delete()

            # Prepend user prefix to the new file name
            if user_prefix:
                new_file_name = f"{user_prefix}{new_file_name}"

            message = await event.respond(f"Your new File name is: {new_file_name}{file_extension}")
            task_data["message_id"] = message.id
            task_data["status"] = "default"
            task_data["file_name"] = new_file_name  # Update the file_name in task_data
            event.client.task_data[task_id] = task_data
            asyncio.create_task(download_and_upload_in_background(event, task_data, user_id))
        else:
            await event.respond("No active rename request found.")
    except Exception as e:
        logging.error(f"Error in rename_process: {e}")
        await event.respond(f"An error occurred. Please try again later")
