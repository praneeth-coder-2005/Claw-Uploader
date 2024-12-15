import logging
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import requests
import os
import aiohttp
import aiofiles
from time import time
from concurrent.futures import ThreadPoolExecutor

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = '7502020526:AAHGAIk6yBS0TL2J1wOpd_-mFN1HorgVc1s'
bot = Bot(token=TOKEN)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Welcome! Send me a URL to download the file.')

def help_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Send a valid URL and I will download and send you the file.')

def handle_url(update: Update, context: CallbackContext) -> None:
    url = update.message.text
    update.message.reply_text('Processing your request...')

    if valid_url(url):
        download_file(url, update.message.chat_id)
    else:
        update.message.reply_text('Invalid URL!')

def valid_url(url):
    try:
        response = requests.head(url)
        return response.status_code == 200
    except:
        return False

def download_file(url, chat_id):
    bot.send_message(chat_id=chat_id, text='Downloading...')
    start_time = time()
    file_name = url.split('/')[-1]

    async def fetch(url, session, chat_id):
        async with session.get(url) as response:
            if response.status == 200:
                file_size = int(response.headers.get('content-length', 0))
                if file_size > MAX_FILE_SIZE:
                    bot.send_message(chat_id=chat_id, text='File size exceeds 2GB limit.')
                    return None

                downloaded = 0
                progress_threshold = file_size // 10
                next_progress_update = progress_threshold
                progress_message = bot.send_message(chat_id=chat_id, text='Download [0%]')

                async with aiofiles.open(file_name, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024):
                        await f.write(chunk)
                        downloaded += len(chunk)

                        if downloaded >= next_progress_update:
                            percentage = (downloaded / file_size) * 100
                            progress_bar = ('█' * (downloaded // progress_threshold)) + ('░' * (10 - (downloaded // progress_threshold)))
                            bot.edit_message_text(chat_id=chat_id, message_id=progress_message.message_id, text=f'Download [{progress_bar}] {percentage:.0f}% complete')
                            next_progress_update += progress_threshold

                return file_name
            else:
                return None

    async def download():
        async with aiohttp.ClientSession() as session:
            file = await fetch(url, session, chat_id)
            if file:
                bot.send_message(chat_id=chat_id, text='Uploading...')
                with open(file, 'rb') as f:
                    bot.send_document(chat_id=chat_id, document=f)
                os.remove(file)
                elapsed_time = time() - start_time
                bot.send_message(chat_id=chat_id, text=f'Completed in {elapsed_time:.2f} seconds!')
            else:
                bot.send_message(chat_id=chat_id, text='Failed to download the file.')

    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(lambda: asyncio.run(download()))

def main():
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('help', help_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_url))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
