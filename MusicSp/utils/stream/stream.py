import os
import random
from typing import Union

from pyrogram.types import InlineKeyboardMarkup

import config
from MusicSp import Carbon, YouTube, app
from MusicSp.core.call import DevSp
from MusicSp.misc import db
from MusicSp.utils.database import add_active_video_chat, is_active_chat, get_lang
from MusicSp.utils.exceptions import AssistantErr
from MusicSp.utils.inline import aq_markup, close_markup, stream_markup
from MusicSp.utils.pastebin import DevSpBin
from MusicSp.utils.stream.queue import put_queue, put_queue_index
from MusicSp.utils.thumbnails import gen_thumb
from strings import get_string


async def autoplay_next_song(client, chat_id):
    """
    Autoplay logic: Search for a similar song and play it when the current one ends.
    """
    playing = db.get(chat_id)
    if not playing:
        return

    track = playing[0]
    if not track.get("autoplay"):
        return

    vidid = track.get("vidid")
    if not vidid or vidid in ["telegram", "soundcloud", "index_url"]:
        return  # Autoplay only works for YouTube/Searchable tracks

    try:
        query = track.get("title")
        if not query:
            return

        # Get language strings for the new stream
        try:
            language = await get_lang(chat_id)
            _ = get_string(language)
        except:
            _ = get_string("en")

        # Search for similar songs
        # Assuming YouTube.slider returns a list of dictionaries with 'vidid', 'title', 'duration_min'
        results = await YouTube.slider(query, 0)  # 0 means random/first page
        if not results:
            print("Autoplay: No similar songs found.")
            return

        # Pick a random similar song
        next_track = random.choice(results)
        next_vidid = next_track.get("vidid")

        # Send a message that autoplay is starting
        mystic = await app.send_message(
            chat_id=chat_id,
            text="ᴀᴜᴛᴏᴘʟᴀʏɪɴɢ ɴᴇxᴛ sᴏɴɢ...",
        )

        # Download next track
        file_path, direct = await YouTube.download(
            next_vidid, mystic, videoid=True, video=False
        )

        # Prepare details for the stream
        details = {
            "title": next_track.get("title"),
            "link": f"https://youtu.be/{next_vidid}",
            "path": file_path,
            "dur": next_track.get("duration_min"),
            "vidid": next_vidid,
            "streamtype": "youtube",
        }

        # Start the stream
        await stream(
            _,
            mystic,
            track.get("user_id"),
            details,
            chat_id,
            track.get("by"),
            chat_id,  # original_chat_id
            streamtype="youtube",
            forceplay=True,
        )
    except Exception as e:
        print(f"Autoplay Error: {e}")


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
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(button),
                    has_spoiler=True,
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
        if count == 0:
            return
        else:
            link = await DevSpBin(msg)
            lines = msg.count("\n")
            if lines >= 17:
                car = os.linesep.join(msg.split(os.linesep)[:17])
            else:
                car = msg
            carbon = await Carbon.generate(car, random.randint(100, 10000000))
            upl = close_markup(_)
            return await app.send_photo(
                original_chat_id,
                photo=carbon,
                caption=_["play_21"].format(position, link),
                reply_markup=upl,
                has_spoiler=True,
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
            return await app.send_message(
                original_chat_id,
                "You can't add more than 10 songs to the queue.",
            )

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
                text=_["queue_4"].format(
                    position, title[:27], duration_min, user_name
                ),
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
            run = await app.send_photo(
                chat_id=original_chat_id,
                photo=img,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(button),
                has_spoiler=True,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"

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
                text=_["queue_4"].format(
                    position, title[:27], duration_min, user_name
                ),
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
            run = await app.send_photo(
                chat_id=original_chat_id,
                photo=config.SOUNCLOUD_IMG_URL,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(button),
                has_spoiler=True,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

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
                text=_["queue_4"].format(
                    position, title[:27], duration_min, user_name
                ),
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
            run = await app.send_photo(
                chat_id=original_chat_id,
                photo=photo,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(button),
                has_spoiler=True,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

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
                text=_["queue_4"].format(
                    position, title[:27], duration_min, user_name
                ),
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
            run = await app.send_photo(
                chat_id=original_chat_id,
                photo=img,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(button),
                has_spoiler=True,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

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
                text=_["queue_4"].format(
                    position, title[:27], duration_min, user_name
                ),
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
            run = await app.send_photo(
                chat_id=original_chat_id,
                photo=config.STREAM_IMG_URL,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(button),
                has_spoiler=True,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
            await mystic.delete()
