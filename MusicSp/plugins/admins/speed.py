from pyrogram import filters
from pyrogram.types import Message

from MusicSp import app
from MusicSp.core.call import DevSp
from MusicSp.misc import SUDOERS, db
from MusicSp.utils import AdminRightsCheck
from MusicSp.utils.database import is_active_chat, is_nonadmin_chat
from MusicSp.utils.decorators.language import languageCB
from MusicSp.utils.inline import close_markup, speed_markup
from config import BANNED_USERS, adminlist

checker = []


async def perform_speed_change(chat_id, speed_type, mention="", callback_query=None):
    playing = db.get(chat_id)
    if not playing:
        if callback_query:
            return await callback_query.answer("Queue is empty!", show_alert=True)
        return

    duration_seconds = int(playing[0]["seconds"])
    if duration_seconds == 0:
        if callback_query:
            return await callback_query.answer("Live stream speed cannot be changed!", show_alert=True)
        return

    file_path = playing[0]["file"]
    if "downloads" not in file_path:
        if callback_query:
            return await callback_query.answer("Only downloaded files can be modified!", show_alert=True)
        return

    if chat_id in checker:
        if callback_query:
            return await callback_query.answer("Please wait, previous speed change is in progress!", show_alert=True)
        return
    else:
        checker.append(chat_id)

    is_slowed = playing[0].get("is_slowed", False)
    is_sped = playing[0].get("is_sped", False)

    if speed_type == "slow":
        if is_slowed:
            speed_type = "normal"
            playing[0]["is_slowed"] = False
        else:
            playing[0]["is_slowed"] = True
            playing[0]["is_sped"] = False
    elif speed_type == "sped":
        if is_sped:
            speed_type = "normal"
            playing[0]["is_sped"] = False
        else:
            playing[0]["is_sped"] = True
            playing[0]["is_slowed"] = False

    if speed_type == "slow":
        speed_val = "0.8"  # Slowed down speed
        txt = f"➻ sʟᴏᴡᴇᴅ ʀᴇᴠᴇʀʙ ᴇɴᴀʙʟᴇᴅ 🎄\n│ \n└ʙʏ : {mention} 🥀"
    elif speed_type == "sped":
        speed_val = "1.2"  # Sped up speed
        txt = f"➻ sᴘᴇᴅ ᴜᴘ ᴇɴᴀʙʟᴇᴅ 🎄\n│ \n└ʙʏ : {mention} 🥀"
    else:
        speed_val = "1.0"  # Normal speed
        txt = f"➻ ɴᴏʀᴍᴀʟ sᴘᴇᴇᴅ ʀᴇsᴛᴏʀᴇᴅ 🎄\n│ \n└ʙʏ : {mention} 🥀"

    try:
        if callback_query:
            await callback_query.answer("Changing speed...", show_alert=False)

        await DevSp.speedup_stream(
            chat_id,
            file_path,
            speed_val,
            playing,
        )
        
        if chat_id in checker:
            checker.remove(chat_id)
            
        if callback_query:
            await callback_query.answer(txt, show_alert=True)
            from MusicSp.utils.inline import refresh_player_markup
            await refresh_player_markup(None, chat_id)
        else:
            await callback_query.message.reply_text(text=txt, reply_markup=close_markup(_))
    except Exception:
        if chat_id in checker:
            checker.remove(chat_id)
        if callback_query:
            return await callback_query.answer("Failed to change speed!", show_alert=True)
        return


@app.on_message(
    filters.command(["cspeed", "speed", "cslow", "slow", "playback", "cplayback"])
    & filters.group
    & ~BANNED_USERS
)
@AdminRightsCheck
async def playback(cli, message: Message, _, chat_id):
    playing = db.get(chat_id)
    if not playing:
        return await message.reply_text(_["queue_2"])
    duration_seconds = int(playing[0]["seconds"])
    if duration_seconds == 0:
        return await message.reply_text(_["admin_27"])
    file_path = playing[0]["file"]
    if "downloads" not in file_path:
        return await message.reply_text(_["admin_27"])
    upl = speed_markup(_, chat_id)
    return await message.reply_text(
        text=_["admin_28"].format(app.mention),
        reply_markup=upl,
    )


@app.on_callback_query(filters.regex("SpeedUP") & ~BANNED_USERS)
@languageCB
async def del_back_playlist(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    chat, speed = callback_request.split("|")
    chat_id = int(chat)
    if not await is_active_chat(chat_id):
        return await CallbackQuery.answer(_["general_5"], show_alert=True)
    is_non_admin = await is_nonadmin_chat(CallbackQuery.message.chat.id)
    if not is_non_admin:
        if CallbackQuery.from_user.id not in SUDOERS:
            admins = adminlist.get(CallbackQuery.message.chat.id)
            if not admins:
                return await CallbackQuery.answer(_["admin_13"], show_alert=True)
            else:
                if CallbackQuery.from_user.id not in admins:
                    return await CallbackQuery.answer(_["admin_14"], show_alert=True)
    
    await perform_speed_change(chat_id, speed, CallbackQuery.from_user.mention, CallbackQuery)
