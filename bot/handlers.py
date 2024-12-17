# handlers.py
import asyncio
import logging
import os
import time
import uuid
import math
import aiohttp
import magic
from telethon import TelegramClient, events, Button
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedDocument, DocumentAttributeFilename
from telethon.utils import get_display_name
from telethon.errors import FloodWaitError

from bot.utils import get_file_name_extension, extract_filename_from_content_disposition
from bot.progress import ProgressBar
from bot.config import BOT_TOKEN, API_ID, API_HASH


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

# Initialize ProgressManager
progress_manager = ProgressManager()


# Main Bot Logic
bot = TelegramClient('bot', API_ID, API_HASH)


@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    try:
        user = await event.get_sender()
        message_text = f"Hello {get_display_name(user)}! 👋\nI'm ready to upload files for you. I will upload upto 2gb.\nJust send me a URL, and I'll handle the rest.\n\nAvailable Commands:\n/start - Start the bot\n/help - Show this message"
        await event.respond(message_text)
    except Exception as e:
        logging.error(f"Error in /start handler: {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    try:
        await event.respond('Available Commands:\n/start - Start the bot\n/help - Show this message')
    except Exception as e:
        logging.error(f"Error in /help handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.NewMessage)
async def url_processing(event):
    try:
        url = event.text.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return  # Ignore non-URL messages

        await event.delete()

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
            logging.error(f"AIOHTTP Error fetching URL {url}: {e}")
            await event.respond(f"Error fetching URL: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while processing URL {url}: {e}")
            await event.respond(f"An error occurred: {e}")
    except Exception as e:
        logging.error(f"Error in url_processing handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.CallbackQuery(data=lambda data: data.decode().startswith('default_')))
async def default_file_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = progress_manager.get_task(task_id)
        if task_data:

            file_name = task_data["file_name"]
            file_extension = task_data["file_extension"]
            file_size = task_data["file_size"]
            url = task_data["url"]
            mime_type = task_data["mime_type"]
            await event.answer(message="Processing file upload..")
            await download_and_upload(event, url, f"{file_name}{file_extension}", file_size, mime_type, task_id, file_extension, event)
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
       if task_id and event.sender_id == event.sender_id:
           
            new_file_name = event.text
            file_extension = task_data["file_extension"]
            file_size = task_data["file_size"]
            url = task_data["url"]
            mime_type = task_data["mime_type"]
            await event.delete()
            await event.respond(f"Your new File name is: {new_file_name}{file_extension}")
            await download_and_upload(event, url, f"{new_file_name}{file_extension}", file_size, mime_type, task_id, file_extension, event)
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


async def download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension, current_event):
    temp_file_path = f"temp_{task_id}"
    try:
        downloaded_size = 0
        start_time = time.time()
        download_speed = 0
        upload_speed = 0

        progress_bar = ProgressBar(file_size, "Processing", bot, current_event, task_id, file_name, file_size)
        task_data = progress_manager.get_task(task_id)
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
                logging.error(f"Download error (attempt {attempt + 1}/{MAX_RETRIES}) from {url}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logging.error(f"Maximum retries reached for download from {url}")
                    await current_event.respond(f"Download Error: {e}. Maximum retries reached.")
                    return
            except Exception as e:
                logging.error(f"An exception occurred in downlaod_and_upload while downloading file : {e}")
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
                
                upload_process = await bot.upload_file(
                    f,
                    chunk_size=upload_chunk_size,
                    progress_callback=lambda current, total: asyncio.create_task(
                        progress_bar.update_progress(current / total))
                    )
                uploaded_size = 0
                elapsed_upload_time = time.time() - start_upload_time
                upload_speed = file_size / elapsed_upload_time if elapsed_upload_time > 0 else 0
                await progress_bar.update_progress(1, download_speed=download_speed, upload_speed=upload_speed)
                try:
                    await bot(SendMediaRequest(
                        peer=await bot.get_input_entity(current_event.chat_id),
                        media=InputMediaUploadedDocument(
                            file=upload_process,
                            mime_type=mime_type,
                            attributes=[
                                DocumentAttributeFilename(file_name)
                            ]
                        ),
                        message=f"File Name: {file_name}{file_extension}",
                    ))
                    await progress_bar.stop("Upload Complete")
                except FloodWaitError as e:
                    logging.warning(f"Flood wait error during upload: {e}")
                    await asyncio.sleep(e.seconds)
                    await download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension, current_event)
                    return
                except Exception as e:
                      logging.error(f"An error occurred during upload: {e}")
                      await current_event.respond(f"An error occurred during upload: {e}")
                      return

        else:
             await current_event.respond(
                f"Error: Download incomplete (Size mismatch) file_size is: {file_size} and downloaded size is: {downloaded_size}")

    except Exception as e:
        logging.error(f"An unexpected error occurred in downlaod_and_upload: {e}")
        await current_event.respond(f"An error occurred: {e}")
    finally:
       progress_manager.remove_task(task_id)
       if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
