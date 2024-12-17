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
from telethon import functions, types

from bot.utils import get_file_name_extension, extract_filename_from_content_disposition
from bot.progress import ProgressBar
from bot.config import BOT_TOKEN, API_ID, API_HASH


logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

# Constants
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4 GB
CHUNK_SIZE = 2 * 1024 * 1024 # 2 MB initial chunk size
MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_FILE_PARTS = 3000

# Globals
progress_messages = {}

# Main Bot Logic
bot = TelegramClient('bot', API_ID, API_HASH)


@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    try:
        user = await event.get_sender()
        message_text = f"Hello {get_display_name(user)}! 👋\nI'm ready to upload files for you. I will upload upto 4gb.\nJust send me a URL, and I'll handle the rest.\n\nAvailable Commands:\n/start - Start the bot\n/help - Show this message"
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
                        await event.respond('File size exceeds the limit of 4GB.')
                        return

                    mime_type = response.headers.get('Content-Type', "application/octet-stream")
                    content_disposition = response.headers.get('Content-Disposition')

                    original_file_name = extract_filename_from_content_disposition(content_disposition)
                    if not original_file_name:
                        file_name, file_extension = get_file_name_extension(url)
                    else:
                        file_name, file_extension = os.path.splitext(original_file_name)
                        
                    task_id = str(uuid.uuid4())
                    progress_messages[task_id] = {
                        "file_name": file_name,
                        "file_extension": file_extension,
                        "file_size": file_size,
                        "url": url,
                        "mime_type": mime_type,
                         "cancel_flag": False
                    }
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
        if task_id in progress_messages:
           
            file_name = progress_messages[task_id]["file_name"]
            file_extension = progress_messages[task_id]["file_extension"]
            file_size = progress_messages[task_id]["file_size"]
            url = progress_messages[task_id]["url"]
            mime_type = progress_messages[task_id]["mime_type"]
            await event.answer(message="Processing file upload..")
            await download_and_upload(event, url, f"{file_name}{file_extension}", file_size, mime_type, task_id, file_extension)
        else:
             await event.answer("No Active Download")
    except Exception as e:
        logging.error(f"Error in default_file_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.CallbackQuery(data=lambda data: data.decode().startswith('rename_')))
async def rename_handler(event):
    try:
         task_id = event.data.decode().split('_')[1]
         if task_id in progress_messages:
            progress_messages[task_id]["status"] = "rename_requested"
            await event.answer(message='Send your desired file name:')
         else:
            await event.answer("No Active Download")

    except Exception as e:
        logging.error(f"Error in rename_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")


@bot.on(events.NewMessage)
async def rename_process(event):
    try:
       for task_id, data in progress_messages.items():
          if "status" in data and data["status"] == "rename_requested" and event.sender_id == event.sender_id:

            new_file_name = event.text
            file_extension = data["file_extension"]
            file_size = data["file_size"]
            url = data["url"]
            mime_type = data["mime_type"]
            await event.delete()
            await event.respond(f"Your new File name is: {new_file_name}{file_extension}")
            await download_and_upload(event, url, f"{new_file_name}{file_extension}", file_size, mime_type, task_id, file_extension)
            return
    except Exception as e:
        logging.error(f"Error in rename_process: {e}")
        await event.respond(f"An error occurred. Please try again later")

@bot.on(events.CallbackQuery(data=lambda data: data.decode().startswith('cancel_')))
async def cancel_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
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

async def upload_file_chunked(client, file_path, chunk_size, progress_callback, total_parts):
    file_size = os.path.getsize(file_path)
    file_id = os.urandom(8)
    offset = 0
    
    with open(file_path, 'rb') as f:
        while offset < file_size:
            
            chunk = f.read(chunk_size)
            if not chunk:
                break
            
            part = offset // chunk_size # Ensure part is integer
            await client(functions.upload.SaveBigFilePartRequest(
                file_id=file_id,
                file_part=int(part),
                file_total_parts=int(total_parts),
                bytes=chunk
            ))
            
            offset += len(chunk)
            if progress_callback:
                await progress_callback(offset, file_size)

    return types.InputFileBig(id=file_id, parts=int(total_parts), name=os.path.basename(file_path))
    

async def download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension):
    temp_file_path = f"temp_{task_id}"
    try:
        downloaded_size = 0
        start_time = time.time()
        download_speed = 0
        upload_speed = 0

        progress_bar = ProgressBar(file_size, "Processing", bot, event, task_id, file_name, file_size)
        progress_messages[task_id]["progress_bar"] = progress_bar

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
                                await progress_bar.update_progress(downloaded_size / file_size, download_speed=download_speed)
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
                
                total_parts = math.ceil(file_size/upload_chunk_size)

                file = await upload_file_chunked(
                      bot,
                      temp_file_path,
                      upload_chunk_size,
                      progress_callback=lambda current, total: asyncio.create_task(
                          progress_bar.update_progress(current / total)),
                      total_parts=total_parts
                    )

            uploaded_size = 0
            elapsed_upload_time = time.time() - start_upload_time
            upload_speed = file_size / elapsed_upload_time if elapsed_upload_time > 0 else 0
            await progress_bar.update_progress(1, download_speed=download_speed, upload_speed=upload_speed)
            uploaded = await bot(SendMediaRequest(
                peer=await bot.get_input_entity(event.chat_id),
                media=InputMediaUploadedDocument(
                    file=file,
                    mime_type=mime_type,
                    attributes=[
                        DocumentAttributeFilename(file_name)
                    ]
                ),
                message='',
            ))
            await progress_bar.stop("Upload Complete")
            await event.respond(uploaded, file=file, caption=f"File Name: {file_name}{file_extension}")
        else:
             await event.respond(
                f"Error: Download incomplete (Size mismatch) file_size is: {file_size} and downloaded size is: {downloaded_size}")

    except Exception as e:
        logging.error(f"An unexpected error occurred in downlaod_and_upload: {e}")
        await event.respond(f"An error occurred: {e}")
    finally:
        if task_id in progress_messages:
            del progress_messages[task_id]
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
