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
from telethon.tl.types import InputMediaUploadedDocument, DocumentAttributeFilename, InputMediaUploadedPhoto, InputFile
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import InputFile, InputMediaUploadedPhoto, InputMedia

from bot.config import MAX_RETRIES, RETRY_DELAY, CHUNK_SIZE, MAX_FILE_PARTS
from bot.progress import ProgressBar
from bot.utils import upload_thumb

async def download_and_upload(event, url, file_name, file_size, mime_type, task_id, file_extension, current_event, user_id, progress_manager):
    temp_file_path = f"temp_{task_id}"
    try:
        downloaded_size = 0
        start_time = time.time()
        download_speed = 0
        upload_speed = 0

        task_data = progress_manager.get_task(task_id)
        if task_data is None:
            logging.error(f"Task data not found for task_id: {task_id}")
            await current_event.respond("Error: Task data not found. Please try again.")
            return

        message_id = task_data.get("message_id")
        progress_bar = task_data["progress_bar"]
        progress_bar.client = event.client
        progress_bar.event = current_event
        if message_id:
            progress_bar.set_message_id(message_id)

        for attempt in range(MAX_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=None) as response:
                        response.raise_for_status()

                        with open(temp_file_path, "wb") as temp_file:
                            while True:
                                if progress_manager.get_cancel_flag(task_id):
                                    logging.info(f"Task {task_id} canceled by user.")
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
                logging.error(f"An exception occurred in download_and_upload while downloading file : {e}, url: {url}")
                await current_event.respond(f"An error occurred : {e}")
                return

        if downloaded_size == file_size:
            upload_task = asyncio.create_task(upload_file(event, temp_file_path, file_name, file_size, mime_type, task_id, file_extension, progress_bar, current_event, user_id))
            await upload_task
        else:
            await current_event.respond(
                f"Error: Download incomplete (Size mismatch) file_size is: {file_size} and downloaded size is: {downloaded_size}")
            logging.error(f"Download incomplete for {url}: expected {file_size} bytes, got {downloaded_size} bytes")

    except Exception as e:
        logging.error(f"An unexpected error occurred in download_and_upload: {e}, url: {url}")
        await current_event.respond(f"An error occurred: {e}")
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        progress_manager.remove_task(task_id)

async def upload_file(event, temp_file_path, file_name, file_size, mime_type, task_id, file_extension, progress_bar, current_event, user_id):
    start_upload_time = time.time()
    try:
        with open(temp_file_path, "rb") as f:
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(temp_file_path)

            parts = math.ceil(file_size / CHUNK_SIZE)
            upload_chunk_size = CHUNK_SIZE
            if parts > MAX_FILE_PARTS:
                upload_chunk_size = math.ceil(file_size / MAX_FILE_PARTS)
                logging.warning(f"Reducing upload chunk size to {upload_chunk_size / (1024*1024):.2f} MB due to excessive parts {parts}")

            thumb = await upload_thumb(current_event, user_id)
            uploaded_thumb = None

            if thumb:
                try:
                    thumb_file = await event.client(GetFileRequest(location=InputFile(id=thumb,
                                                                                        access_hash=0,
                                                                                        file_reference=b'')))
                    uploaded_thumb = await event.client.upload_file(thumb_file.bytes)
                    thumb = InputMediaUploadedPhoto(file=uploaded_thumb)


                except Exception as e:
                    logging.error(f"Error fetching thumbnail: {e}")
                    thumb = None

            file = await event.client.upload_file(
                f,
                file_name=file_name,
                progress_callback=lambda current, total: progress_bar.update_progress(current / total)
            )

            elapsed_upload_time = time.time() - start_upload_time
            upload_speed = file_size / elapsed_upload_time if elapsed_upload_time > 0 else 0
            await progress_bar.update_progress(1, upload_speed=upload_speed)

            media = InputMediaUploadedDocument(
                file=file,
                mime_type=mime_type,
                attributes=[DocumentAttributeFilename(file_name)],
                thumb=thumb if isinstance(thumb, InputMedia) else None
            )


            await event.client(SendMediaRequest(
                peer=await event.client.get_input_entity(current_event.chat_id),
                media=media,
                message=f"File Name: {file_name}",
            ))
            await progress_bar.stop("Upload Complete")

    except FloodWaitError as e:
        logging.warning(f"Flood wait error during upload: {e}")
        await asyncio.sleep(e.seconds)
        await upload_file(event, temp_file_path, file_name, file_size, mime_type, task_id, file_extension, progress_bar, current_event, user_id)
    except Exception as e:
        logging.error(f"An error occurred during upload: {e}")
        await current_event.respond(f"An error occurred during upload: {e}")
