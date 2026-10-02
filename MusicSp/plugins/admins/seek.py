from pyrogram import filters
from pyrogram.types import Message

from MusicSp import YouTube, app
from MusicSp.core.call import DevSp
from MusicSp.misc import db
from MusicSp.utils import AdminRightsCheck, seconds_to_min
from MusicSp.utils.inline import close_markup
from config import BANNED_USERS


async def perform_seek(chat_id, skip_seconds, backward=True, mention="", callback_query=None):
    playing = db.get(chat_id)
    if not playing:
        if callback_query:
            return await callback_query.answer("Queue is empty!", show_alert=True)
        return

    duration_seconds = int(playing[0]["seconds"])
    if duration_seconds == 0:
        if callback_query:
            return await callback_query.answer("Live stream cannot be seeked!", show_alert=True)
        return

    file_path = playing[0]["file"]
    duration_played = int(playing[0]["played"])
    duration_to_skip = int(skip_seconds)
    duration = playing[0]["dur"]

    if backward:
        if (duration_played - duration_to_skip) <= 10:
            msg = f"ᴛᴏᴏ ʟᴇss ᴛɪᴍᴇ ᴛᴏ sᴇᴇᴋ ʙᴀᴄᴋᴡᴀʀᴅ\n\nᴘʟᴀʏᴇᴅ : {seconds_to_min(duration_played)} | ᴅᴜʀᴀᴛɪᴏɴ : {duration}"
            if callback_query:
                return await callback_query.answer(msg, show_alert=True)
            return
        to_seek = duration_played - duration_to_skip + 1
    else:
        if (duration_seconds - (duration_played + duration_to_skip)) <= 10:
            msg = f"ᴛᴏᴏ ʟᴇss ᴛɪᴍᴇ ᴛᴏ sᴇᴇᴋ ғᴏʀᴡᴀʀᴅ\n\nᴘʟᴀʏᴇᴅ : {seconds_to_min(duration_played)} | ᴅᴜʀᴀᴛɪᴏɴ : {duration}"
            if callback_query:
                return await callback_query.answer(msg, show_alert=True)
            return
        to_seek = duration_played + duration_to_skip + 1

    if "vid_" in file_path:
        n, file_path = await YouTube.video(playing[0]["vidid"], True)
        if n == 0:
            return

    check = (playing[0]).get("speed_path")
    if check:
        file_path = check
    if "index_" in file_path:
        file_path = playing[0]["vidid"]

    try:
        await DevSp.seek_stream(
            chat_id,
            file_path,
            seconds_to_min(to_seek),
            duration,
            playing[0]["streamtype"],
        )
    except Exception:
        if callback_query:
            return await callback_query.answer("Failed to seek stream!", show_alert=True)
        return

    if backward:
        db[chat_id][0]["played"] -= duration_to_skip
    else:
        db[chat_id][0]["played"] += duration_to_skip

    if callback_query:
        await callback_query.answer(f"Seeked to {seconds_to_min(to_seek)}", show_alert=True)
    else:
        await callback_query.message.reply_text(
            text=f"➻ sᴇᴇᴋᴇᴅ ᴛᴏ {seconds_to_min(to_seek)} 🎄\n│ \n└ʙʏ : {mention} 🥀",
            reply_markup=close_markup(_),
        )


@app.on_message(
    filters.command(["seek", "cseek", "seekback", "cseekback"])
    & filters.group
    & ~BANNED_USERS
)
@AdminRightsCheck
async def seek_comm(cli, message: Message, _, chat_id):
    if len(message.command) == 1:
        return await message.reply_text(_["admin_20"])
    query = message.text.split(None, 1)[1].strip()
    if not query.isnumeric():
        return await message.reply_text(_["admin_21"])
    
    backward = True if message.command[0][-2] == "c" else False
    await perform_seek(chat_id, int(query), backward=backward, mention=message.from_user.mention)
