# bot/handlers/settings.py
import logging
from telethon import events
from bot.utils import set_user_setting, get_user_settings
from bot.services.progress import ProgressManager
from telethon.tl.types import DocumentAttributeFilename
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedPhoto

progress_manager = ProgressManager()

async def handle_settings_input(event):
    user_id = event.sender_id
    status = progress_manager.get_task(user_id)

    if status:
        if status["status"] == "set_thumbnail":
            if event.media:
                try:
                    # Download the thumbnail photo sent by the user
                    thumb_file = await event.client.download_media(event.media, file="bot/")
                    
                    # Upload the thumbnail photo
                    file = await event.client.upload_file(thumb_file, file_name="thumbnail.jpg")
                    
                    # Get photo ID
                    photo = await event.client(
                        SendMediaRequest(
                            peer=await event.client.get_input_entity(event.chat_id),
                            media=InputMediaUploadedPhoto(file=file),
                            message="Thumbnail set!"
                        )
                    )
                    
                    # Extract the file ID from the photo object
                    file_id = photo.photo.id
                    
                    # Save the thumbnail file ID in settings
                    set_user_setting(user_id, "thumbnail", file_id)
                    await event.respond("Thumbnail updated!")
                    
                    # Clean up: remove the temporary thumbnail file
                    os.remove(thumb_file)

                except Exception as e:
                    logging.error(f"Error setting thumbnail: {e}")
                    await event.respond("Error setting thumbnail. Please try again.")
            else:
                await event.respond("Please send me an image to use as a thumbnail.")
            
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

        progress_manager.remove_task(user_id)
