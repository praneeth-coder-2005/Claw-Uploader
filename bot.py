import logging
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import requests
import os
from celery import Celery
from aiohttp import ClientSession
import aiofiles
from redis import Redis
from time import time
from concurrent.futures import ThreadPoolExecutor

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = '7502020526:AAHGAIk6yBS0TL2J1wOpd_-mFN1HorgVc1s'
REDIS_URL = 'redis://localhost:6379/0'
bot = Bot(token=TOKEN)
app = Celery('tasks', broker=REDIS_URL)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

# Set up Redis
redis_conn = Redis.from_url(REDIS_URL)

# Rate limiting: Limit to 5 requests per hour per user
RATE_LIMIT = 5
RATE_LIMIT_DURATION = 3600  # 1 hour

def rate_limited(user_id):
    count = redis_conn.get(f'rate_limit_{user_id}')
    if count is None:
        redis_conn.set(f'rate_limit_{user_id}', 1, ex=RATE_LIMIT_DURATION)
        return False
    elif int(count) < RATE_LIMIT:
        redis_conn.incr(f'rate_limit_{user_id}')
        return False
    else:
        return True

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Welcome! Send me a URL to download the file.')

def help_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Send a valid URL and I will download and send you the file.')

def handle_url(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if rate_limited(user_id):
        update.message.reply_text('You have exceeded the request limit. Please try again later.')
        return

    url = update.message.text
    update.message.reply_text('Processing your request...')

    if valid_url(url):
        task = download_file.delay(url, update.message.chat_id)
        context.bot.send_message(chat_id=update.effective_chat.id, text=f'Queued task with ID: {task.id}')
    else:
        update.message.reply_text('Invalid URL!')

def valid_url(url):
    try:
        response = requests.head(url)
        return response.status_code == 200
    except:
        return False

@app.task(bind=True)
def download_file(self, url, chat_id):
    start_time = time()
    file_name = url.split('/')[-1]

    async def fetch(url, session):
        async with session.get(url) as response:
            if response.status == 200:
                file_size = int(response.headers.get('content-length', 0))
                if file_size > MAX_FILE_SIZE:
                    bot.send_message(chat_id=chat_id, text='File size exceeds 2GB limit.')
                    return None
                async with aiofiles.open(file_name, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024):
                        await f.write(chunk)
                return file_name
            else:
                return None

    async def download():
        async with ClientSession() as session:
            file = await fetch(url, session)
            if file:
                bot.send_message(chat_id=chat_id, text='Uploading...')
                with open(file, 'rb') as f:
                    bot.send_document(chat_id=chat_id, document=f)
                os.remove(file)
                elapsed_time = time() - start_time
                bot.send_message(chat_id=chat_id, text=f'Completed in {elapsed_time:.2f} seconds!')
            else:
                bot.send_message(chat_id=chat_id, text='Failed to download the file.')

    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(download())

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
