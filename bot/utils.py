import os
import re
from urllib.parse import urlparse, unquote
import logging
import json
import aiohttp
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedPhoto
from bot.config import DEFAULT_THUMBNAIL

SETTINGS_FILE = "bot/settings.json"  # Path to your settings file

def get_file_name_extension(url):
    try:
        parsed_url = urlparse(url)
        file_name = os.path.basename(parsed_url.path)
        file_name = unquote(file_name)
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

def extract_filename_from_content_disposition(content_disposition):
    if not content_disposition:
        return None

    filename_match = re.search(r'filename="([^"]+)"', content_disposition)
    if filename_match:
        return filename_match.group(1)

    filename_star_match = re.search(r"filename\*=UTF-8''([^;]*)", content_disposition)
    if filename_star_match:
        return filename_star_match.group(1)

    return None

def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

def get_user_settings(user_id):
    settings = load_settings()
    return settings.get(str(user_id), {
        "thumbnail": None,
        "prefix": None,
        "rename_rules": []
    })

def set_user_setting(user_id, key, value):
    settings = load_settings()
    user_id_str = str(user_id)
    if user_id_str not in settings:
        settings[user_id_str] = {
            "thumbnail": None,
            "prefix": None,
            "rename_rules": []
        }
    settings[user_id_str][key] = value
    save_settings(settings)

async def upload_thumb(event, user_id, file=None):
    user_settings = get_user_settings(user_id)
    thumbnail_id = user_settings.get("thumbnail")
    if file:
        try:
            uploaded_file = await event.client.upload_file(file)
            return uploaded_file.id # Returning file id instead of InputSizedFile
        except Exception as e:
            logging.error(f"Error uploading thumbnail file : {e}")
            return None
    if thumbnail_id:
            return thumbnail_id

    return None
