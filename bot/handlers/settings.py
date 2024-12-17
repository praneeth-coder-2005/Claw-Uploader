# handlers/settings.py
from telethon import events
from bot.utils import set_user_setting
from bot.services.progress import ProgressManager

progress_manager = ProgressManager()

async def handle_settings_input(event):
    user_id = event.sender_id
    status = progress_manager.get_task(user_id)

    if status:
        if status["status"] == "set_thumbnail":
            thumbnail_url = event.text.strip()
            set_user_setting(user_id, "thumbnail", thumbnail_url)
            await event.respond(f"Thumbnail set to: {thumbnail_url}")
            progress_manager.remove_task(user_id)

        elif status["status"] == "set_prefix":
            new_prefix = event.text.strip()
            set_user_setting(user_id, "prefix", new_prefix)
            await event.respond(f"Prefix set to: {new_prefix}")
            progress_manager.remove_task(user_id)

        elif status["status"] == "add_rename_rule":
            new_rule = event.text.strip()
            user_settings = get_user_settings(user_id)
            user_settings["rename_rules"].append(new_rule)
            set_user_setting(user_id, "rename_rules", user_settings["rename_rules"])
            await event.respond(f"Added rename rule: {new_rule}")
            progress_manager.remove_task(user_id)
