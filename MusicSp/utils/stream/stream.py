import os
import traceback
from random import randint
from typing import Union

from pyrogram.raw import types as raw_types
from pyrogram.types import InlineKeyboardMarkup, InputRichMessage

import config
from MusicSp import Carbon, YouTube, app
from MusicSp.core.call import DevSp
from MusicSp.misc import db
from MusicSp.utils.database import add_active_video_chat, is_active_chat
from MusicSp.utils.exceptions import AssistantErr
from MusicSp.utils.inline import aq_markup, close_markup, stream_markup
from MusicSp.utils.pastebin import DevSpBin
from MusicSp.utils.stream.queue import put_queue, put_queue_index
from MusicSp.utils.thumbnails import gen_thumb


async def _send_rich_stream_msg(app, chat_id, photo, caption, duration_min, button):
    """
    Rich message bhejne ke liye helper.
    """
    try:
        # 1. Photo ko temporarily bhejein taaki InputPhoto ke liye zaroori details mil sakein
        temp_msg = await app.send_photo(chat_id=chat_id, photo=photo)
        photo_obj = temp_msg.photo

        # 2. Sahi InputPhoto object banayein (save_file ke bajaye)
        input_photo = raw_types.InputPhoto(
            id=photo_obj.file_id,
            access_hash=photo_obj.access_hash,
            file_reference=photo_obj.file_reference
        )

        # 3. Temporary photo ko turant delete karein taaki chat mein double thumbnail na dikhe
        await temp_msg.delete()

        # 4. Standard inline buttons ko PageBlockButtonRow mein convert karein
        button_rows = []
        for row in button:
            page_buttons = []
            for btn in row:
                if btn.callback_data:
                    btn_type = raw_types.InlineButtonTypeCallback(
                        data=btn.callback_data.encode()
                    )
                elif btn.url:
                    btn_type = raw_types.InlineButtonTypeUrl(url=btn.url)
                else:
                    continue

                page_buttons.append(
                    raw_types.PageButton(
                        text=raw_types.TextPlain(text=btn.text),
                        type=btn_type,
                        style=raw_types.RichButtonStyle(bg_primary=True)
                    )
                )
            if page_buttons:
                button_rows.append(
                    raw_types.PageBlockButtonRow(
                        buttons=page_buttons,
                        align_center=True
                    )
                )

        # 5. Rich blocks banayein (Photo + Caption + Progress Bar + Buttons)
        # 🔥 FIX: TextRich ki jagah TextPlain use karein
        rich_blocks = [
            raw_types.PageBlockPhoto(
                photo_id=input_photo.id,
                caption=raw_types.PageCaption(
                    text=raw_types.TextPlain(text=caption)
                )
            ),
            raw_types.PageBlockProgressBar(
                progress=0,
                text=raw_types.TextPlain(text=f"00:00 / {duration_min}")
            )
        ]
        rich_blocks.extend(button_rows)

        # 6. Rich message bhejein (photos list pass karna zaroori hai)
        return await app.send_rich_message(
            chat_id=chat_id,
            rich_message=InputRichMessage(
                blocks=rich_blocks,
                photos=[input_photo]
            )
        )
    except Exception as e:
        # 🔥 Error print karein taaki Heroku logs mein asli dikkat dikhe
        print(f"❌ RICH MESSAGE FAILED: {e}")
        traceback.print_exc()

        # Fallback: agar rich message fail ho to normal photo bhej dein
        return await app.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(button)
        )


async def stream(
    _,
    mystic,
    user_id,
    result,
    chat_id,
    user_name,
    original_chat_id,
    video: Union[bool, str] = None,
    streamtype: Union[bool, str] = None,
    spotify: Union[bool, str] = None,
    forceplay: Union[bool, str] = None,
):
    if not result:
        return
    if forceplay:
        await DevSp.force_stop_stream(chat_id)
    if streamtype == "playlist":
        msg = f"{_['play_19']}\n\n"
        count = 0
        for search in result:
            if int(count) == config.PLAYLIST_FETCH_LIMIT:
                continue
            try:
                (
                    title,
                    duration_min,
                    duration_sec,
                    thumbnail,
                    vidid,
                ) = await YouTube.details(search, False if spotify else True)
            except:
                continue
            if str(duration_min) == "None":
                continue
            if duration_sec > config.DURATION_LIMIT:
                continue
            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if video else "audio",
                )
                position = len(db.get(chat_id)) - 1
                count += 1
                msg += f"{count}. {title[:70]}\n"
                msg += f"{_['play_20']} {position}\n\n"
            else:
                if not forceplay:
                    db[chat_id] = []
                status = True if video else None
                try:
                    file_path, direct = await YouTube.download(
                        vidid, mystic, video=status, videoid=True
                    )
                except Exception:
                    raise AssistantErr(_["play_14"])
                if not file_path:
                    raise AssistantErr(_["play_14"])
                await DevSp.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=status,
                    image=thumbnail,
                )
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path if direct else f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if video else "audio",
                    forceplay=forceplay,
                )
                img = await gen_thumb(vidid)
                button = stream_markup(_, chat_id)
                caption = _["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23],
                    duration_min,
                    user_name,
                )
                run = await _send_rich_stream_msg(app, original_chat_id, img, caption, duration_min, button)
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
                db[chat_id][0]["photo"] = img
                db[chat_id][0]["caption"] = caption
        if count == 0:
            return
        else:
            link = await DevSpBin(msg)
            lines = msg.count("\n")
            if lines >= 17:
                car = os.linesep.join(msg.split(os.linesep)[:17])
            else:
                car = msg
            carbon = await Carbon.generate(car, randint(100, 10000000))
            upl = close_markup(_)
            return await app.send_photo(
                original_chat_id,
                photo=carbon,
                caption=_["play_21"].format(position, link),
                reply_markup=upl,
            )
    elif streamtype == "youtube":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        duration_min = result["duration_min"]
        thumbnail = result["thumb"]
        status = True if video else None
    
        current_queue = db.get(chat_id)

        if current_queue is not None and len(current_queue) >= 10:
            return await app.send_message(original_chat_id, "You can't add more than 10 songs to the queue.")

        try:
            file_path, direct = await YouTube.download(
                vidid, mystic, videoid=True, video=status
            )
        except Exception:
            raise AssistantErr(_["play_14"])
        if not file_path:
            raise AssistantErr(_["play_14"])

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await DevSp.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=status,
                image=thumbnail,
            )
            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            img = await gen_thumb(vidid)
            button = stream_markup(_, chat_id)
            caption = _["stream_1"].format(
                f"https://t.me/{app.username}?start=info_{vidid}",
                title[:23],
                duration_min,
                user_name,
            )
            run = await _send_rich_stream_msg(app, original_chat_id, img, caption, duration_min, button)
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"
            db[chat_id][0]["photo"] = img
            db[chat_id][0]["caption"] = caption
    elif streamtype == "soundcloud":
        file_path = result["filepath"]
        title = result["title"]
        duration_min = result["duration_min"]
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await DevSp.join_call(chat_id, original_chat_id, file_path, video=None)
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
                forceplay=forceplay,
            )
            button = stream_markup(_, chat_id)
            caption = _["stream_1"].format(
                config.SUPPORT_GROUP, title[:23], duration_min, user_name
            )
            run = await _send_rich_stream_msg(app, original_chat_id, config.SOUNCLOUD_IMG_URL, caption, duration_min, button)
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
            db[chat_id][0]["photo"] = config.SOUNCLOUD_IMG_URL
            db[chat_id][0]["caption"] = caption
    elif streamtype == "telegram":
        file_path = result["path"]
        link = result["link"]
        title = (result["title"]).title()
        duration_min = result["dur"]
        status = True if video else None
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await DevSp.join_call(chat_id, original_chat_id, file_path, video=status)
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            if video:
                await add_active_video_chat(chat_id)
            button = stream_markup(_, chat_id)
            photo = config.TELEGRAM_VIDEO_URL if video else config.TELEGRAM_AUDIO_URL
            caption = _["stream_1"].format(link, title[:23], duration_min, user_name)
            run = await _send_rich_stream_msg(app, original_chat_id, photo, caption, duration_min, button)
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
            db[chat_id][0]["photo"] = photo
            db[chat_id][0]["caption"] = caption
    elif streamtype == "live":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        thumbnail = result["thumb"]
        duration_min = "Live Track"
        status = True if video else None
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            n, file_path = await YouTube.video(link)
            if n == 0:
                raise AssistantErr(_["str_3"])
            await DevSp.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=status,
                image=thumbnail if thumbnail else None,
            )
            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            img = await gen_thumb(vidid)
            button = stream_markup(_, chat_id)
            caption = _["stream_1"].format(
                f"https://t.me/{app.username}?start=info_{vidid}",
                title[:23],
                duration_min,
                user_name,
            )
            run = await _send_rich_stream_msg(app, original_chat_id, img, caption, duration_min, button)
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
            db[chat_id][0]["photo"] = img
            db[chat_id][0]["caption"] = caption
    elif streamtype == "index":
        link = result
        title = "ɪɴᴅᴇx ᴏʀ ᴍ3ᴜ8 ʟɪɴᴋ"
        duration_min = "00:00"
        if await is_active_chat(chat_id):
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await mystic.edit_text(
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await DevSp.join_call(
                chat_id,
                original_chat_id,
                link,
                video=True if video else None,
            )
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            button = stream_markup(_, chat_id)
            caption = _["stream_2"].format(user_name)
            run = await _send_rich_stream_msg(app, original_chat_id, config.STREAM_IMG_URL, caption, duration_min, button)
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
            db[chat_id][0]["photo"] = config.STREAM_IMG_URL
            db[chat_id][0]["caption"] = caption
            await mystic.delete()
