# bot/progress.py
import time
import asyncio
import logging
from telethon import Button

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
        self.download_speed = 0
        self.upload_speed = 0
        self.average_download_speed_buffer = []
        self.average_upload_speed_buffer = []
        self.message_id = None

    def set_message_id(self, message_id):
        self.message_id = message_id

    def update_average_speed(self, speed, buffer):
        buffer.append(speed)
        if len(buffer) > 5:
            buffer.pop(0)
        return sum(buffer) / len(buffer) if buffer else 0

    async def update_progress(self, progress, download_speed=None, upload_speed=None):
        try:
            self.current = int(progress * self.total)
            percentage = int((self.current / self.total) * 100)

            if self.done:
                return

            if (percentage - self.last_sent_progress) >= 5 or percentage == 100:
                now = time.time()
                if self.current > 0 and (now - self.last_update_time > 0.5):  # Prevent excessive updates
                    elapsed_time = now - self.start_time

                    if percentage != 0:
                        time_remaining = ((self.total - self.current) / (self.current / elapsed_time))
                        estimated_time_str = f"{int(time_remaining)}s" if time_remaining < 60 else f"{int(time_remaining / 60)}m {int(time_remaining % 60)}s"

                        if download_speed is not None:
                            self.download_speed = self.update_average_speed(download_speed, self.average_download_speed_buffer)
                        if upload_speed is not None:
                            self.upload_speed = self.update_average_speed(upload_speed, self.average_upload_speed_buffer)

                        download_speed_str = f" {self.download_speed / 1024:.2f} KB/s" if self.download_speed else ""
                        upload_speed_str = f" {self.upload_speed / 1024:.2f} KB/s" if self.upload_speed else ""

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
                                    logging.warning(f"Flood Wait detected in edit message, waiting to retry: {e}")
                                    await asyncio.sleep(int(str(e).split(" ")[-1]))
                                    await self.update_progress(progress, download_speed, upload_speed)
                                else:
                                    logging.error(f"Failed to edit progress message: {e}, message id: {self.message}")
                        else:
                            try:
                                self.message = await self.client.send_message(self.event.chat_id, message_text,
                                                                    buttons=[[Button.inline("Cancel", data=f"cancel_{self.task_id}")]])
                            except Exception as e:
                                if "FloodWait" in str(e):
                                    logging.warning(f"Flood Wait detected in send message, waiting to retry: {e}")
                                    await asyncio.sleep(int(str(e).split(" ")[-1]))
                                    await self.update_progress(progress, download_speed, upload_speed)
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
                    logging.warning(f"Flood Wait detected in stop message, waiting to retry: {e}")
                    await asyncio.sleep(int(str(e).split(" ")[-1]))
                    await self.stop(text)
                else:
                    logging.error(f"Failed to edit final message: {e}, message id: {self.message}")
        else:
            try:
                await self.client.send_message(self.event.chat_id, text)
            except Exception as e:
                if "FloodWait" in str(e):
                    logging.warning(f"Flood Wait detected in stop message, waiting to retry: {e}")
                    await asyncio.sleep(int(str(e).split(" ")[-1]))
                    await self.stop(text)
                else:
                    logging.error(f"Failed to send final message: {e}")
