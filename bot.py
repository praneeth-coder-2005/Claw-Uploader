import os
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)
from telegram.constants import ChatAction
from time import time

# Function to format file size
def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

# Start command
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Help", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Welcome to the bot! Use the buttons below:", reply_markup=reply_markup)

# Help command
def help_command(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Upload URL", callback_data="upload_url")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Choose an option:", reply_markup=reply_markup)

# Callback query handler
def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data == "help":
        help_command(update, context)
    elif query.data == "upload_url":
        query.message.reply_text("Please send the URL of the file you want to upload:")

# Handle URL input
def handle_url(update: Update, context: CallbackContext):
    url = update.message.text
    try:
        # Fetch file metadata
        response = requests.head(url, allow_redirects=True)
        file_size = int(response.headers.get('content-length', 0))
        file_name = os.path.basename(url.split("?")[0])

        # Send options to user
        keyboard = [
            [InlineKeyboardButton("Default", callback_data=f"default|{file_name}|{file_size}")],
            [InlineKeyboardButton("Rename", callback_data=f"rename|{file_name}|{file_size}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(
            f"File detected:\n\nTitle: {file_name}\nSize: {format_size(file_size)}\n\nChoose an option:",
            reply_markup=reply_markup,
        )
    except Exception as e:
        update.message.reply_text(f"Error fetching file metadata: {e}")

# Handle rename or default option
def handle_file_option(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data.split("|")
    action, file_name, file_size = data[0], data[1], int(data[2])

    if action == "default":
        download_file(query, file_name, file_size, context)
    elif action == "rename":
        context.user_data["file_name"] = file_name
        context.user_data["file_size"] = file_size
        query.message.reply_text("Send the new file name (without extension):")

# Handle renaming
def handle_rename(update: Update, context: CallbackContext):
    new_name = update.message.text
    file_name = context.user_data["file_name"]
    file_size = context.user_data["file_size"]

    # Preserve original extension
    extension = os.path.splitext(file_name)[1]
    new_file_name = f"{new_name}{extension}"

    # Start download
    download_file(update.message, new_file_name, file_size, context)

# Download and upload file with progress bar
def download_file(message, file_name, file_size, context):
    url = message.text if isinstance(message, Update) else message.reply_to_message.text
    temp_file = f"temp_{file_name}"
    chunk_size = 1024 * 1024  # 1MB
    downloaded = 0
    start_time = time()

    # Download file
    with requests.get(url, stream=True) as r, open(temp_file, "wb") as f:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)

                # Update progress
                percentage = (downloaded / file_size) * 100
                if int(percentage) % 10 == 0:  # Update every 10%
                    elapsed_time = time() - start_time
                    speed = downloaded / elapsed_time
                    eta = (file_size - downloaded) / speed
                    message.reply_text(
                        f"Downloading: {file_name}\n"
                        f"Progress: {percentage:.2f}%\n"
                        f"Speed: {format_size(speed)}/s\n"
                        f"ETA: {eta:.2f}s",
                        parse_mode="Markdown",
                    )

    # Simulate upload (replace with actual upload logic)
    uploaded = 0
    while uploaded < file_size:
        uploaded += chunk_size
        percentage = (uploaded / file_size) * 100
        if int(percentage) % 10 == 0:  # Update every 10%
            message.reply_text(
                f"Uploading: {file_name}\n"
                f"Progress: {percentage:.2f}%",
                parse_mode="Markdown",
            )

    # Cleanup
    os.remove(temp_file)
    message.reply_text(f"File {file_name} uploaded successfully!")

# Main function
def main():
    updater = Updater("7502020526:AAHGAIk6yBS0TL2J1wOpd_-mFN1HorgVc1s")
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CallbackQueryHandler(button))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_url))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_rename))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
