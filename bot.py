import asyncio
import logging
import os
import time
import uuid
from urllib.parse import urlparse
import traceback

import aiohttp
import magic
from telethon import TelegramClient, events, Button
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedDocument, DocumentAttributeFilename
from telethon.utils import get_display_name

from config import API_ID, API_HASH, BOT_TOKEN  # Import configuration from config.py

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

# Constants
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
CHUNK_SIZE = 1024 * 1024  # 1 MB
PROGRESS_UPDATE_INTERVAL = 10  # Update every 10% complete
MAX_RETRIES = 3  # Max retries for download failures
RETRY_DELAY = 5  # Delay between retries in seconds
FLOOD_WAIT_THRESHOLD = 60

# Globals
progress_messages = {}


# Get original filename and extension from URL
def get_file_name_extension(url):
    try:
        parsed_url = urlparse(url)
        file_name = os.path.basename(parsed_url.path)
        name_parts = file_name.split('.')
        if len(name_parts) > 1:
            file_extension = '.' + name_parts[-1]
            file_name = ".".join(name_parts[:-1])
        else:
            file_extension = ''
        return file_name, file_extension
    except Exception as e:
        logging.error(f"Error getting filename/extension: {e}, url: {url}")
        return "unknown", ""


# Custom progress bar class
class ProgressBar:
    def __init__(self, total, description, client, event, task_id, file_name, file_size):
        self.total = total
        self.current = 0
        self.start_time = time.time()
        self.description = description
        self.last_update_time = 0
        self.client = client
        self.event = event
        self.task_id = task_id
        self.file_name = file_name
        self.file_size = file_size
        self.message = None
        self.start_time = time.time()
        self.last_sent_progress = 0
        self.done = False

    async def update_progress(self, progress, upload_speed=None, download_speed=None):
        try:
            self.current = int(progress * self.total)
            percentage = int((self.current / self.total) * 100)

            if self.done:
                return

            if (percentage - self.last_sent_progress) >= PROGRESS_UPDATE_INTERVAL or percentage == 100:
                now = time.time()
                if self.current > 0 and (now - self.last_update_time > 0.5):  # Prevent excessive updates
                    elapsed_time = now - self.start_time

                    if percentage != 0:
                        time_remaining = ((self.total - self.current) / (self.current / elapsed_time))
                        estimated_time_str = f"{int(time_remaining)}s" if time_remaining < 60 else f"{int(time_remaining / 60)}m {int(time_remaining % 60)}s"

                        download_speed_str = f" {download_speed / 1024:.2f} KB/s" if download_speed else ""
                        upload_speed_str = f" {upload_speed / 1024:.2f} KB/s" if upload_speed else ""

                        message_text = f"**{self.description}: {self.file_name}**\n"
                        message_text += f"File Size: {self.file_size / (1024 * 1024):.2f} MB\n"
                        message_text += f"Download Speed: {download_speed_str} Upload Speed: {upload_speed_str}\n"
                        message_text += f"ETA: {estimated_time_str}\n"
                        message_text += f"[{'#' * int(percentage / 10) + '-' * (10 - int(percentage / 10))}] {percentage}%"

                        if self.message:
                            try:
                                await self.client.edit_message(self.event.chat_id, self.message, message_text,
                                                                buttons=[[Button.inline("Cancel", data=f"cancel_{self.task_id}")]])
                            except Exception as e:
                                if "FloodWait" in str(e):
                                    logging.warning(f"Flood Wait detected in edit message : {e}")
                                else:
                                    logging.error(f"Failed to edit progress message: {e}, message id: {self.message}")
                        else:
                            try:
                                self.message = await self.client.send_message(self.event.chat_id, message_text,
                                                                    buttons=[[Button.inline("Cancel", data=f"cancel_{self.task_id}")]])
                            except Exception as e:
                                if "FloodWait" in str(e):
                                    logging.warning(f"Flood Wait detected in send message : {e}")
                                else:
                                    logging.error(f"Failed to send progress message: {e}")

                    self.last_update_time = now
                    self.last_sent_progress = percentage
        except Exception as e:
            logging.error(f"Error in update progress method: {e}")

    async def stop(self, text="Canceled"):
        self.done = True
        if self.message:
            try:
                await self.client.edit_message(self.event.chat_id, self.message, text)
            except Exception as e:
                if "FloodWait" in str(e):
                    logging.warning(f"Flood Wait detected in stop message : {e}")
                else:
                    logging.error(f"Failed to edit final message: {e}, message id: {self.message}")
        else:
            try:
                await self.client.send_message(self.event.chat_id, text)
            except Exception as e:
                if "FloodWait" in str(e):
                    logging.warning(f"Flood Wait detected in stop message : {e}")
                else:
                    logging.error(f"Failed to send final message: {e}")


# Main Bot Logic
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    try:
        user = await event.get_sender()
        await event.respond(
            f"Hello {get_display_name(user)}! 👋\n I'm ready to upload files for you. I will upload upto 2gb and follow the given commands.")
        await event.respond('Use /help to see available options.')
    except Exception as e:
        logging.error(f"Error in /start handler: {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    try:
        await event.respond('Available Commands:\n/start - Start the bot\n/help - Show this message',
                            buttons=[[Button.inline("Upload URL", data="upload_url")]])
    except Exception as e:
        logging.error(f"Error in /help handler: {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.CallbackQuery(data="upload_url"))
async def url_handler(event):
    try:
        await event.answer('Please give url to Upload', show_alert=True)
        progress_messages[event.sender_id] = {"status": "url_requested"}
    except Exception as e:
        logging.error(f"Error in url_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.NewMessage)
async def url_processing(event):
    try:
        if event.sender_id in progress_messages and progress_messages[event.sender_id]["status"] == "url_requested":
            url = event.text
            progress_messages[event.sender_id] = {"status": "processing_url", "url": url}
            await event.delete()
            file_name, file_extension = get_file_name_extension(url)

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(url, allow_redirects=True, timeout=10) as response:
                        response.raise_for_status()
                        file_size = int(response.headers.get('Content-Length', 0))

                        if file_size > MAX_FILE_SIZE:
                            await event.respond('File size exceeds the limit of 2GB.')
                            del progress_messages[event.sender_id]
                            return

                        mime_type = response.headers.get('Content-Type', "application/octet-stream")

                        buttons = [[Button.inline("Default", data=f"default_{event.sender_id}"),
                                    Button.inline("Rename", data=f"rename_{event.sender_id}")]]
                        await event.respond(
                            f"Original File Name: {file_name}{file_extension}\nFile Size: {file_size / (1024 * 1024):.2f} MB",
                            buttons=buttons)

                        progress_messages[event.sender_id]["file_name"] = file_name
                        progress_messages[event.sender_id]["file_extension"] = file_extension
                        progress_messages[event.sender_id]["file_size"] = file_size
                        progress_messages[event.sender_id]["mime_type"] = mime_type
            except aiohttp.ClientError as e:
                logging.error(f"AIOHTTP Error fetching URL {url}: {e}")
                await event.respond(f"Error fetching URL: {e}")
                del progress_messages[event.sender_id]
            except Exception as e:
                logging.error(f"An unexpected error occurred while processing URL {url}: {e}")
                await event.respond(f"An error occurred: {e}")
                del progress_messages[event.sender_id]
    except Exception as e:
        logging.error(f"Error in url_processing handler : {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.CallbackQuery(data=lambda data: data.startswith('default_')))
async def default_file_handler(event):
    try:
        sender_id = int(event.data.split('_')[1])
        if sender_id in progress_messages and progress_messages[sender_id]["status"] == "processing_url":
            file_name = progress_messages[sender_id]["file_name"]
            file_extension = progress_messages[sender_id]["file_extension"]
            file_size = progress_messages[sender_id]["file_size"]
            url = progress_messages[sender_id]["url"]
            mime_type = progress_messages[sender_id]["mime_type"]
            await event.answer("Processing file upload..")
            await download_and_upload(event, url, f"{file_name}{file_extension}", file_size, mime_type)
            del progress_messages[sender_id]
    except Exception as e:
        logging.error(f"Error in default_file_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.CallbackQuery(data=lambda data: data.startswith('rename_')))
async def rename_handler(event):
    try:
        sender_id = int(event.data.split('_')[1])
        if sender_id in progress_messages and progress_messages[sender_id]["status"] == "processing_url":
            progress_messages[sender_id]["status"] = "rename_requested"
            await event.answer('Send your desired file name:')
    except Exception as e:
        logging.error(f"Error in rename_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.NewMessage)
async def rename_process(event):
    try:
        if event.sender_id in progress_messages and progress_messages[event.sender_id]["status"] == "rename_requested":
            new_file_name = event.text
            file_extension = progress_messages[event.sender_id]["file_extension"]
            file_size = progress_messages[event.sender_id]["file_size"]
            url = progress_messages[event.sender_id]["url"]
            mime_type = progress_messages[event.sender_id]["mime_type"]
            await event.delete()
            await event.respond(f"Your new File name is: {new_file_name}{file_extension}")
            await download_and_upload(event, url, f"{new_file_name}{file_extension}", file_size, mime_type)
            del progress_messages[event.sender_id]
    except Exception as e:
        logging.error(f"Error in rename_process: {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.CallbackQuery(data=lambda data: data.startswith('cancel_')))
async def cancel_handler(event):
    try:
        task_id = event.data.split('_')[1]
        if task_id in progress_messages:

            progress_message = progress_messages[task_id]
            if "cancel_flag" in progress_message:
                progress_message["cancel_flag"] = True
            await progress_message["progress_bar"].stop("Canceled by User")
            del progress_messages[task_id]
            await event.answer("Upload Canceled")
        else:
            await event.answer("No active download to cancel.")
    except Exception as e:
        logging.error(f"Error in cancel_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")


async def download_and_upload(event, url, file_name, file_size, mime_type):
    task_id = str(uuid.uuid4())
    progress_messages[task_id] = {"cancel_flag": False}
    temp_file_path = f"temp_{task_id}"
    try:
        downloaded_size = 0
        start_time = time.time()
        download_speed = 0

        download_progress = ProgressBar(file_size, "Downloading", bot, event, task_id, file_name, file_size)
        progress_messages[task_id]["progress_bar"] = download_progress

        for attempt in range(MAX_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=None) as response:
                        response.raise_for_status()

                        with open(temp_file_path, "wb") as temp_file:
                            while True:
                                if progress_messages[task_id]["cancel_flag"]:
                                    return

                                chunk = await response.content.readany()
                                if not chunk:
                                    break

                                start_chunk_time = time.time()
                                temp_file.write(chunk)
                                downloaded_size += len(chunk)
                                elapsed_time = time.time() - start_time
                                if elapsed_time > 0:
                                    download_speed = downloaded_size / elapsed_time

                                await download_progress.update_progress(downloaded_size / file_size,
                                                                          download_speed=download_speed)
                        break
            except aiohttp.ClientError as e:
                logging.error(f"Download error (attempt {attempt + 1}/{MAX_RETRIES}) from {url}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logging.error(f"Maximum retries reached for download from {url}")
                    await event.respond(f"Download Error: {e}. Maximum retries reached.")
                    return
            except Exception as e:
                logging.error(f"An exception occurred in downlaod_and_upload while downloading file : {e}")
                await event.respond(f"An error occurred : {e}")
                return

        if downloaded_size == file_size:
            upload_progress = ProgressBar(file_size, "Uploading", bot, event, task_id, file_name, file_size)
            progress_messages[task_id]["progress_bar"] = upload_progress
            await upload_file(event, temp_file_path, file_name, file_size, mime_type, upload_progress, task_id)
        else:
            await event.respond(
                f"Error: Download incomplete (Size missmatch) file_size is: {file_size} and downloaded size is: {downloaded_size}")
    except Exception as e:
        logging.error(f"An unexpected error occurred in downlaod_and_upload: {e}")
        await event.respond(f"An error occurred: {e}")
    finally:
        if task_id in progress_messages:
            del progress_messages[task_id]
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


async def upload_file(event, file_path, file_name, file_size, mime_type, progress_bar, task_id):
    try:
        start_time = time.time()
        uploaded_size = 0
        upload_speed = 0
        
        with open(file_path, "rb") as f:
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(file_path)

            file = await bot.upload_file(f, progress_callback=lambda current, total: asyncio.create_task(
                progress_bar.update_progress(current / total)))

        uploaded = await bot(SendMediaRequest(
            peer = await bot.get_input_entity(event.chat_id),
            media=InputMediaUploadedDocument(
                file=file,
                mime_type=mime_type,
                attributes=[
                    DocumentAttributeFilename(file_name)
                ]
            )
        ))

        await progress_bar.stop("Upload Complete")

    except Exception as e:
        logging.error(f"Upload Error: {e}")
        await event.respond(f"Upload Error: {e}")
    finally:
        if task_id in progress_messages:
            del progress_messages[task_id]


async def main():
    try:
        await bot.run_until_disconnected()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"An error occurred in main: {e}")
    finally:
        await bot.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
