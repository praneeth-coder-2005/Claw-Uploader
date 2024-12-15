import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from time import time

# Function to format file size
def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Help", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to the bot! Use the buttons below:", reply_markup=reply_markup)

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Upload URL", callback_data="upload_url")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose an option:", reply_markup=reply_markup)

# Callback query handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        await help_command(update, context)
    elif query.data == "upload_url":
        await query.message.reply_text("Please send the URL of the file you want to upload:")

# Handle URL input
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(
            f"File detected:\n\nTitle: {file_name}\nSize: {format_size(file_size)}\n\nChoose an option:",
            reply_markup=reply_markup,
        )
    except Exception as e:
        await update.message.reply_text(f"Error fetching file metadata: {e}")

# Handle rename or default option
async def handle_file_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    action, file_name, file_size = data[0], data[1], int(data[2])

    if action == "default":
        await download_file(query.message, file_name, file_size, context)
    elif action == "rename":
        context.user_data["file_name"] = file_name
        context.user_data["file_size"] = file_size
        await query.message.reply_text("Send the new file name (without extension):")

# Handle renaming
async def handle_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text
    file_name = context.user_data["file_name"]
    file_size = context.user_data["file_size"]

    # Preserve original extension
    extension = os.path.splitext(file_name)[1]
    new_file_name = f"{new_name}{extension}"

    # Start download
    await download_file(update.message, new_file_name, file_size, context)

# Download and upload file with progress bar
async def download_file(message, file_name, file_size, context):
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
                    await message.reply_text(
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
            await message.reply_text(
                f"Uploading: {file_name}\n"
                f"Progress: {percentage:.2f}%",
                parse_mode="Markdown",
            )

    # Cleanup
    os.remove(temp_file)
    await message.reply_text(f"File {file_name} uploaded successfully!")

# Main function
async def main():
    application = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rename))

    await application.run_polling()

if __name__ == "__main__":
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # No running event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
