# handlers/callbacks.py
import logging
from telethon import events, Button
from bot.services.progress import ProgressManager
from bot.utils import get_user_settings, set_user_setting
from bot.config import DEFAULT_PREFIX

progress_manager = ProgressManager()

async def set_thumbnail_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "set_thumbnail")
    await event.respond("Please send me the thumbnail URL:")

async def set_prefix_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "set_prefix")
    await event.respond("Please send me the new prefix:")

async def add_rename_rule_handler(event):
    user_id = event.sender_id
    progress_manager.update_task_status(user_id, "add_rename_rule")
    await event.respond("Please send me the text to remove from filenames:")

async def remove_rename_rule_handler(event):
    user_id = event.sender_id
    user_settings = get_user_settings(user_id)
    if user_settings["rename_rules"]:
        progress_manager.update_task_status(user_id, "remove_rename_rule")
        buttons = [
            [Button.inline(rule, data=f"remove_rule_{i}")]
            for i, rule in enumerate(user_settings["rename_rules"])
        ]
        await event.respond("Which rule do you want to remove?", buttons=buttons)
    else:
        await event.answer("You don't have any rename rules set.")

async def remove_rule_callback_handler(event):
    user_id = event.sender_id
    rule_index = int(event.data.decode().split("_")[-1])
    user_settings = get_user_settings(user_id)
    if 0 <= rule_index < len(user_settings["rename_rules"]):
        removed_rule = user_settings["rename_rules"].pop(rule_index)
        set_user_setting(user_id, "rename_rules", user_settings["rename_rules"])
        await event.answer(f"Removed rule: {removed_rule}")
        await settings_handler(event)
    else:
        await event.answer("Invalid rule index.")

async def done_settings_handler(event):
    await event.answer("Settings saved!")
    await event.delete()

async def default_file_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = progress_manager.get_task(task_id)
        user_id = event.sender_id
        if task_data:
            user_settings = get_user_settings(user_id)
            user_prefix = user_settings.get("prefix", DEFAULT_PREFIX)

            file_name = task_data["file_name"]
            file_extension = task_data["file_extension"]
            file_size = task_data["file_size"]
            url = task_data["url"]
            mime_type = task_data["mime_type"]

            # Apply rename rules
            for rule in user_settings["rename_rules"]:
                file_name = file_name.replace(rule, "")
            
            message = await event.respond(message="Processing file upload..")
            progress_manager.set_message_id(task_id, message.id)

            await download_and_upload(event, url, f"{user_prefix}{file_name}{file_extension}", file_size, mime_type, task_id, file_extension, event, user_id)
        else:
             await event.answer("No Active Download")
    except Exception as e:
        logging.error(f"Error in default_file_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

async def rename_handler(event):
    try:
         task_id = event.data.decode().split('_')[1]
         if progress_manager.get_task(task_id):
            progress_manager.update_task_status(task_id, "rename_requested")
            await event.answer(message='Send your desired file name:')
         else:
            await event.answer("No Active Download")

    except Exception as e:
        logging.error(f"Error in rename_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")

async def cancel_handler(event):
    try:
        task_id = event.data.decode().split('_')[1]
        task_data = progress_manager.get_task(task_id)
        if task_data:
            progress_manager.set_cancel_flag(task_id, True)
            await task_data["progress_bar"].stop("Canceled by User")
            progress_manager.remove_task(task_id)
            await event.answer("Upload Canceled")
        else:
            await event.answer("No active download to cancel.")
    except Exception as e:
        logging.error(f"Error in cancel_handler: {e}")
        await event.respond(f"An error occurred. Please try again later")
