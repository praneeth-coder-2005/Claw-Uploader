# bot/config.py

BOT_TOKEN = "7502020526:AAHGAIk6yBS0TL2J1wOpd_-mFN1HorgVc1s"  # Replace with your bot token from @BotFather
API_ID = "22250562"  # Replace with your API ID
API_HASH = "07754d3bdc27193318ae5f6e6c8016af"  # Replace with your API Hash

DEFAULT_THUMBNAIL = "https://envs.sh/Rdy.jpg"  # Default thumbnail URL (can be changed in settings)
DEFAULT_PREFIX = "@ClawMoviez - "  # Default prefix for filenames (can be changed in settings)

# File handling settings (for downloads and uploads)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
CHUNK_SIZE = 2 * 1024 * 1024  # 2 MB
MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_FILE_PARTS = 3000
