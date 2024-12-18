from telethon import events, Button, types  # Import types
from bot.utils import get_user_settings, set_user_setting, upload_thumb
import logging
import os
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedPhoto

async def settings_handler(event):
    user_id = event.sender_id
    user_settings = get_user_settings(user_id)
    message = (
        "Current Settings:\n\n"
        f"🖼️ **Thumbnail:** {user_settings['thumbnail'] if user_settings['thumbnail'] else 'Default'}\n"
        f"✍️ **Prefix:** {user_settings['prefix'] if user_settings['prefix'] else 'Default'}\n"
        f"✏️ **Rename Rules:** {', '.join(user_settings['rename_rules']) if user_settings['rename_rules'] else 'None'}\n\n"
        "What do you want to change?"
    )
    buttons = [
        [Button.inline("🖼️ Set Thumbnail", data="set_thumbnail")],
        [Button.inline("✍️ Set Prefix", data="set_prefix")],
        [Button.inline("✏️ Add Rename Rule", data="add_rename_rule")],
        [Button.inline("❌ Remove Rename Rule", data="remove_rename_rule")],
        [Button.inline("✅ Done", data="done_settings")]]
    await event.respond(message, buttons=buttons)

async def set_thumbnail_handler(event):
    user_id = event.sender_id
    event.client.task_data = event.client.task_data if hasattr(event.client, 'task_data') else {}
    event.client.task_data.setdefault(str(user_id), {}).update({"status": "set_thumbnail"})
    await event.answer(message="Please send me the image to use as a thumbnail:")

async def set_prefix_handler(event):
    user_id = event.sender_id
    event.client.task_data = event.client.task_data if hasattr(event.client, 'task_data') else {}
    event.client.task_data.setdefault(str(user_id), {}).update({"status": "set_prefix"})
    await event.answer(message="Please send me the new prefix:")

async def add_rename_rule_handler(event):
    user_id = event.sender_id
    event.client.task_data = event.client.task_data if hasattr(event.client, 'task_data') else {}
    event.client.task_data.setdefault(str(user_id), {}).update({"status": "add_rename_rule"})
    await event.answer(message="Please send me the text to remove from filenames:")

async def remove_rename_rule_handler(event):
    user_id = event.sender_id
    user_settings = get_user_settings(user_id)
    event.client.task_data = event.client.task_data if hasattr(event.client, 'task_data') else {}
    if user_settings["rename_rules"]:
        event.client.task_data.setdefault(str(user_id), {}).update({"status": "remove_rename_rule"})
        buttons = [[Button.inline(rule, data=f"remove_rule_{i}")] for i, rule in enumerate(user_settings["rename_rules"])]
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
        await settings_handler(event)  # Refresh settings
    else:
        await event.answer("Invalid rule index.")

async def done_settings_handler(event):
    await event.answer("Settings saved!")
    await event.delete()


async def process_settings_input(event):
    user_id = event.sender_id
    event.client.task_data = event.client.task_data if hasattr(event.client, 'task_data') else {}
    task_data = event.client.task_data.get(str(user_id), {})
    status = task_data.get("status")

    if status == "set_thumbnail":
            if event.media:
                if isinstance(event.media, types.MessageMediaPhoto):
                    try:
                        file = await event.client.download_media(event.media)
                        thumb_file_id = await upload_thumb(event,user_id, file)
                        set_user_setting(user_id, "thumbnail", thumb_file_id)
                        await event.respond("Thumbnail updated!")
                        if os.path.exists(file):
                            os.remove(file)
                    except Exception as e:
                        logging.error(f"Error in process_settings_input set_thumbnail: {e}")
                        await event.respond("Error updating thumbnail. Please try again later")
                else:
                    await event.respond("Please send a valid image for the thumbnail.")
            else:
                await event.respond("Please send a valid image for the thumbnail.")
            if str(user_id) in event.client.task_data:
                del event.client.task_data[str(user_id)]
            await settings_handler(event)

    elif status == "set_prefix":
            new_prefix = event.text.strip()
            set_user_setting(user_id, "prefix", new_prefix)
            await event.respond(f"Prefix updated to: {new_prefix}")
            if str(user_id) in event.client.task_data:
                  del event.client.task_data[str(user_id)]
            await settings_handler(event)

    elif status == "add_rename_rule":
            rule = event.text.strip()
            user_settings = get_user_settings(user_id)
            if rule not in user_settings["rename_rules"]:
                user_settings["rename_rules"].append(rule)
                set_user_setting(user_id, "rename_rules", user_settings["rename_rules"])
                await event.respond(f"Added rename rule: {rule}")
            else:
                await event.respond(f"Rule already exists: {rule}")
            if str(user_id) in event.client.task_data:
                del event.client.task_data[str(user_id)]
            await settings_handler(event)
