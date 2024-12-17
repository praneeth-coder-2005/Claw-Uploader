# utils.py
import os
import re
from urllib.parse import urlparse, unquote
import logging


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
