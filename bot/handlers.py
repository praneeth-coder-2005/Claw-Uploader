# bot/upload_downloader.py

import asyncio
import logging
import os
import time
import math
import aiohttp
import magic

from telethon import types
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedDocument, DocumentAttributeFilename

from bot.config import MAX_RETRIES, RETRY_DELAY, CHUNK_SIZE, MAX_FILE_PARTS
from bot.utils import upload_thumb
from bot.services.progress_manager import ProgressManager
from bot.progress import ProgressBar

progress_manager = ProgressManager()

async def download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension, current_event, user_id):
    temp_file_path = f"temp_{task_id}"
    try:
        downloaded_size = 0
        start_time = time.time()
        download_speed = 0
        upload_speed = 0

        task_data = progress_manager.get_task(task_id)

        # Robust check for task_data
        if task_data is None:
            logging.error(f"Task data not found for task_id: {task_id}")
            await current_event.respond("Error: Task data not found. Please try again.")
            return

        message_id = task_data.get("message_id")
        progress_bar = ProgressBar(file_size, "Processing", event.client, current_event, task_id, file_name, file_size)
        if message_id:
            progress_bar.set_message_id(message_id)
        
        # Update progress_manager.progress_messages directly
        task_data["progress_bar"] = progress_bar
        progress_manager.progress_messages[task_id] = task_data
        
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
