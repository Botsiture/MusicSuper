import asyncio

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
else:
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

import os
import time
from datetime import datetime, timedelta
from typing import Union

from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup
from pytgcalls import PyTgCalls, StreamType
from pytgcalls.exceptions import (
    AlreadyJoinedError,
    NoActiveGroupCall,
    TelegramServerError,
)
from pytgcalls.types import Update
from pytgcalls.types.input_stream import AudioPiped, AudioVideoPiped
from pytgcalls.types.input_stream.quality import (
    HighQualityAudio,
    HighQualityVideo,
    MediumQualityVideo,
    LowQualityVideo,
)
from pytgcalls.types.stream import StreamAudioEnded

# Apply PyTgCalls MTProto compatibility patches
import MusicSp.core.patch

import config
from MusicSp import LOGGER, YouTube, app
from MusicSp.misc import db
from MusicSp.utils.database import (
    add_active_chat,
    add_active_video_chat,
    get_lang,
    get_loop,
    group_assistant,
    is_autoend,
    music_on,
    remove_active_chat,
    remove_active_video_chat,
    set_loop,
)
from MusicSp.utils.exceptions import AssistantErr
from MusicSp.utils.formatters import check_duration, seconds_to_min, speed_converter
from MusicSp.utils.inline.play import stream_markup
from MusicSp.utils.stream.autoclear import auto_clean
from MusicSp.utils.thumbnails import gen_thumb
from strings import get_string

autoend = {}
counter = {}

# ============================================================
#  🛡️ GRACE PERIOD GUARD
#  PyTgCalls sometimes fires on_left right after join (false
#  positive). Track join time per chat and ignore on_left
#  events coming within GRACE seconds.
# ============================================================
_recently_joined: dict = {}
_RECENT_JOIN_GRACE = 10  # seconds


# ============================================================
#  ⚡ SMOOTH VC STREAM PARAMS
#  HighQualityAudio = 48kHz / stereo / 128kbps.
#  Note: -max_delay was causing early stream termination on
#  some pytgcalls builds, so it is removed.
# ============================================================
SMOOTH_FFMPEG = "-nostdin -threads 2 -bufsize 512k"

HQ_AUDIO = HighQualityAudio()
HQ_VIDEO = HighQualityVideo()
MQ_VIDEO = MediumQualityVideo()


def _audio_stream(file_path, extra_ffmpeg=None):
    """Smooth high-quality audio-only stream."""
    params = SMOOTH_FFMPEG
    if extra_ffmpeg:
        params = f"{extra_ffmpeg} {params}"
    return AudioPiped(
        file_path,
        audio_parameters=HQ_AUDIO,
        additional_ffmpeg_parameters=params,
    )


def _video_stream(file_path, extra_ffmpeg=None, hq_video=False):
    """Smooth audio+video stream."""
    params = SMOOTH_FFMPEG
    if extra_ffmpeg:
        params = f"{extra_ffmpeg} {params}"
    return AudioVideoPiped(
        file_path,
        audio_parameters=HQ_AUDIO,
        video_parameters=HQ_VIDEO if hq_video else MQ_VIDEO,
        additional_ffmpeg_parameters=params,
    )


async def _clear_(chat_id):
    db[chat_id] = []
    await remove_active_video_chat(chat_id)
    await remove_active_chat(chat_id)


class Call(PyTgCalls):
    def __init__(self):
        self.userbot1 = Client(
            name="DevSpAss1",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING1),
        )
        self.one = PyTgCalls(self.userbot1)

        self.userbot2 = Client(
            name="DevSpAss2",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING2),
        )
        self.two = PyTgCalls(self.userbot2)

        self.userbot3 = Client(
            name="DevSpAss3",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING3),
        )
        self.three = PyTgCalls(self.userbot3)

        self.userbot4 = Client(
            name="DevSpAss4",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING4),
        )
        self.four = PyTgCalls(self.userbot4)

        self.userbot5 = Client(
            name="DevSpAss5",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING5),
        )
        self.five = PyTgCalls(self.userbot5)

    async def pause_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        await assistant.pause_stream(chat_id)

    async def resume_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        await assistant.resume_stream(chat_id)

    async def stop_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        _recently_joined.pop(chat_id, None)
        try:
            await _clear_(chat_id)
            await assistant.leave_group_call(chat_id)
        except Exception:
            pass

    async def stop_stream_force(self, chat_id: int):
        try:
            if config.STRING1:
                await self.one.leave_group_call(chat_id)
        except Exception:
            pass
        try:
            if config.STRING2:
                await self.two.leave_group_call(chat_id)
        except Exception:
            pass
        try:
            if config.STRING3:
                await self.three.leave_group_call(chat_id)
        except Exception:
            pass
        try:
            if config.STRING4:
                await self.four.leave_group_call(chat_id)
        except Exception:
            pass
        try:
            if config.STRING5:
                await self.five.leave_group_call(chat_id)
        except Exception:
            pass
        _recently_joined.pop(chat_id, None)
        try:
            await _clear_(chat_id)
        except Exception:
            pass

    async def speedup_stream(self, chat_id: int, file_path, speed, playing):
        assistant = await group_assistant(self, chat_id)
        if str(speed) != str("1.0"):
            base = os.path.basename(file_path)
            chatdir = os.path.join(os.getcwd(), "playback", str(speed))
            if not os.path.isdir(chatdir):
                os.makedirs(chatdir, exist_ok=True)
            out = os.path.join(chatdir, base)
            if not os.path.isfile(out):
                if str(speed) == str("0.5"):
                    vs = 2.0
                elif str(speed) == str("0.75"):
                    vs = 1.35
                elif str(speed) == str("1.5"):
                    vs = 0.68
                elif str(speed) == str("2.0"):
                    vs = 0.5
                else:
                    vs = 1.0
                proc = await asyncio.create_subprocess_shell(
                    cmd=(
                        "ffmpeg -y -hide_banner -loglevel error "
                        f"-i {file_path} "
                        f"-filter:a atempo={speed} "
                        f"-vn {out}"
                    ),
                    stdin=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
        else:
            out = file_path

        dur = await asyncio.get_event_loop().run_in_executor(
            None, check_duration, out
        )
        dur = int(dur)
        played, con_seconds = speed_converter(playing[0]["played"], speed)
        duration = seconds_to_min(dur)

        extra = f"-ss {played} -to {duration}"
        if playing[0]["streamtype"] == "video":
            stream = _video_stream(out, extra_ffmpeg=extra, hq_video=True)
        else:
            stream = _audio_stream(out, extra_ffmpeg=extra)

        if str(db[chat_id][0]["file"]) == str(file_path):
            await assistant.change_stream(chat_id, stream)
        else:
            raise AssistantErr("Umm")

        if str(db[chat_id][0]["file"]) == str(file_path):
            exis = (playing[0]).get("old_dur")
            if not exis:
                db[chat_id][0]["old_dur"] = db[chat_id][0]["dur"]
                db[chat_id][0]["old_second"] = db[chat_id][0]["seconds"]
            db[chat_id][0]["played"] = con_seconds
            db[chat_id][0]["dur"] = duration
            db[chat_id][0]["seconds"] = dur
            db[chat_id][0]["speed_path"] = out
            db[chat_id][0]["speed"] = speed

    async def force_stop_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        try:
            check = db.get(chat_id)
            check.pop(0)
        except Exception:
            pass
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        _recently_joined.pop(chat_id, None)
        try:
            await assistant.leave_group_call(chat_id)
        except Exception:
            pass

    async def skip_stream(
        self,
        chat_id: int,
        link: str,
        video: Union[bool, str] = None,
        image: Union[bool, str] = None,
    ):
        assistant = await group_assistant(self, chat_id)
        if video:
            stream = _video_stream(link, hq_video=True)
        else:
            stream = _audio_stream(link)
        await assistant.change_stream(chat_id, stream)

    async def seek_stream(self, chat_id, file_path, to_seek, duration, mode):
        assistant = await group_assistant(self, chat_id)
        extra = f"-ss {to_seek} -to {duration}"
        if mode == "video":
            stream = _video_stream(file_path, extra_ffmpeg=extra, hq_video=True)
        else:
            stream = _audio_stream(file_path, extra_ffmpeg=extra)
        await assistant.change_stream(chat_id, stream)

    async def stream_call(self, link):
        assistant = await group_assistant(self, config.LOG_GROUP_ID)
        _recently_joined[config.LOG_GROUP_ID] = time.time()
        await assistant.join_group_call(
            config.LOG_GROUP_ID,
            _video_stream(link),
            stream_type=StreamType().pulse_stream,
        )
        await asyncio.sleep(0.2)
        await assistant.leave_group_call(config.LOG_GROUP_ID)

    async def join_call(
        self,
        chat_id: int,
        original_chat_id: int,
        link,
        video: Union[bool, str] = None,
        image: Union[bool, str] = None,
    ):
        assistant = await group_assistant(self, chat_id)
        language = await get_lang(chat_id)
        _ = get_string(language)

        if video:
            stream = _video_stream(link, hq_video=True)
        else:
            stream = _audio_stream(link)

        try:
            await assistant.join_group_call(
                chat_id,
                stream,
                stream_type=StreamType().pulse_stream,
            )
            # 🛡️ Mark join time so false on_left within grace period is ignored
            _recently_joined[chat_id] = time.time()
            LOGGER(__name__).info(f"[JOIN_OK] chat={chat_id}")
        except NoActiveGroupCall:
            LOGGER(__name__).error(f"[JOIN_FAIL] NoActiveGroupCall chat={chat_id}")
            raise AssistantErr(_["call_8"])
        except AlreadyJoinedError:
            LOGGER(__name__).error(f"[JOIN_FAIL] AlreadyJoined chat={chat_id}")
            raise AssistantErr(_["call_9"])
        except TelegramServerError:
            LOGGER(__name__).error(f"[JOIN_FAIL] TelegramServerError chat={chat_id}")
            raise AssistantErr(_["call_10"])
        except Exception as e:
            LOGGER(__name__).error(
                f"[JOIN_FAIL] {type(e).__name__}: {e} chat={chat_id}",
                exc_info=True,
            )
            raise AssistantErr(f"Join failed: {type(e).__name__}: {e}")

        await add_active_chat(chat_id)
        await music_on(chat_id)
        if video:
            await add_active_video_chat(chat_id)
        if await is_autoend():
            counter[chat_id] = {}
            users = len(await assistant.get_participants(chat_id))
            if users == 1:
                autoend[chat_id] = datetime.now() + timedelta(minutes=1)

    async def change_stream(self, client, chat_id):
        check = db.get(chat_id)
        popped = None
        loop = await get_loop(chat_id)
        try:
            if loop == 0:
                popped = check.pop(0)
            else:
                loop = loop - 1
                await set_loop(chat_id, loop)
            await auto_clean(popped)
            if not check:
                await _clear_(chat_id)
                return await client.leave_group_call(chat_id)
        except Exception:
            try:
                await _clear_(chat_id)
                return await client.leave_group_call(chat_id)
            except Exception:
                return
        else:
            queued = check[0]["file"]
            language = await get_lang(chat_id)
            _ = get_string(language)
            title = (check[0]["title"]).title()
            user = check[0]["by"]
            original_chat_id = check[0]["chat_id"]
            streamtype = check[0]["streamtype"]
            videoid = check[0]["vidid"]
            db[chat_id][0]["played"] = 0
            exis = (check[0]).get("old_dur")
            if exis:
                db[chat_id][0]["dur"] = exis
                db[chat_id][0]["seconds"] = check[0]["old_second"]
                db[chat_id][0]["speed_path"] = None
                db[chat_id][0]["speed"] = 1.0

            video = True if str(streamtype) == "video" else False

            if "live_" in queued:
                n, link = await YouTube.video(videoid, True)
                if n == 0:
                    return await app.send_message(
                        original_chat_id,
                        text=_["call_6"],
                    )
                stream = (
                    _video_stream(link, hq_video=True)
                    if video
                    else _audio_stream(link)
                )
                try:
                    await client.change_stream(chat_id, stream)
                except Exception:
                    return await app.send_message(
                        original_chat_id,
                        text=_["call_6"],
                    )
                img = await gen_thumb(videoid)
                button = stream_markup(_, chat_id)
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(
                        f"https://t.me/{app.username}?start=info_{videoid}",
                        title[:23],
                        check[0]["dur"],
                        user,
                    ),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"

            elif "vid_" in queued:
                mystic = await app.send_message(original_chat_id, _["call_7"])
                try:
                    file_path, direct = await YouTube.download(
                        videoid,
                        mystic,
                        videoid=True,
                        video=True if str(streamtype) == "video" else False,
                    )
                except Exception:
                    return await mystic.edit_text(
                        _["call_6"], disable_web_page_preview=True
                    )
                stream = (
                    _video_stream(file_path, hq_video=True)
                    if video
                    else _audio_stream(file_path)
                )
                try:
                    await client.change_stream(chat_id, stream)
                except Exception:
                    return await app.send_message(
                        original_chat_id,
                        text=_["call_6"],
                    )
                img = await gen_thumb(videoid)
                button = stream_markup(_, chat_id)
                await mystic.delete()
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(
                        f"https://t.me/{app.username}?start=info_{videoid}",
                        title[:23],
                        check[0]["dur"],
                        user,
                    ),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"

            elif "index_" in queued:
                stream = (
                    _video_stream(videoid, hq_video=True)
                    if str(streamtype) == "video"
                    else _audio_stream(videoid)
                )
                try:
                    await client.change_stream(chat_id, stream)
                except Exception:
                    return await app.send_message(
                        original_chat_id,
                        text=_["call_6"],
                    )
                button = stream_markup(_, chat_id)
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=config.STREAM_IMG_URL,
                    caption=_["stream_2"].format(user),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"

            else:
                stream = (
                    _video_stream(queued, hq_video=True)
                    if video
                    else _audio_stream(queued)
                )
                try:
                    await client.change_stream(chat_id, stream)
                except Exception:
                    return await app.send_message(
                        original_chat_id,
                        text=_["call_6"],
                    )

                if videoid == "telegram":
                    button = stream_markup(_, chat_id)
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=config.TELEGRAM_AUDIO_URL
                        if str(streamtype) == "audio"
                        else config.TELEGRAM_VIDEO_URL,
                        caption=_["stream_1"].format(
                            config.SUPPORT_GROUP,
                            title[:23],
                            check[0]["dur"],
                            user,
                        ),
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "tg"

                elif videoid == "soundcloud":
                    button = stream_markup(_, chat_id)
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=config.SOUNCLOUD_IMG_URL,
                        caption=_["stream_1"].format(
                            config.SUPPORT_GROUP,
                            title[:23],
                            check[0]["dur"],
                            user,
                        ),
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "tg"

                else:
                    img = await gen_thumb(videoid)
                    button = stream_markup(_, chat_id)
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=img,
                        caption=_["stream_1"].format(
                            f"https://t.me/{app.username}?start=info_{videoid}",
                            title[:23],
                            check[0]["dur"],
                            user,
                        ),
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"

    async def ping(self):
        pings = []
        if config.STRING1:
            pings.append(await self.one.ping)
        if config.STRING2:
            pings.append(await self.two.ping)
        if config.STRING3:
            pings.append(await self.three.ping)
        if config.STRING4:
            pings.append(await self.four.ping)
        if config.STRING5:
            pings.append(await self.five.ping)
        return str(round(sum(pings) / len(pings), 3)) if pings else "0"

    async def start(self):
        LOGGER(__name__).info("Starting PyTgCalls Client...\n")
        if config.STRING1:
            await self.one.start()
        if config.STRING2:
            await self.two.start()
        if config.STRING3:
            await self.three.start()
        if config.STRING4:
            await self.four.start()
        if config.STRING5:
            await self.five.start()

    async def decorators(self):
        # ============================================================
        #  KICKED / VC CLOSED → real leave, stop immediately
        # ============================================================
        @self.one.on_kicked()
        @self.two.on_kicked()
        @self.three.on_kicked()
        @self.four.on_kicked()
        @self.five.on_kicked()
        @self.one.on_closed_voice_chat()
        @self.two.on_closed_voice_chat()
        @self.three.on_closed_voice_chat()
        @self.four.on_closed_voice_chat()
        @self.five.on_closed_voice_chat()
        async def stream_kicked_handler(_, chat_id: int):
            LOGGER(__name__).warning(
                f"[on_kicked/closed_voice_chat] chat={chat_id}"
            )
            _recently_joined.pop(chat_id, None)
            try:
                await self.stop_stream(chat_id)
            except Exception as e:
                LOGGER(__name__).error(f"stop_stream error: {e}")

        # ============================================================
        #  ON_LEFT → with grace period guard
        #  PyTgCalls sometimes fires on_left right after joining.
        #  Ignore events coming within _RECENT_JOIN_GRACE seconds.
        # ============================================================
        @self.one.on_left()
        @self.two.on_left()
        @self.three.on_left()
        @self.four.on_left()
        @self.five.on_left()
        async def stream_left_handler(_, chat_id: int):
            joined_at = _recently_joined.get(chat_id, 0)
            elapsed = time.time() - joined_at
            if joined_at and elapsed < _RECENT_JOIN_GRACE:
                LOGGER(__name__).info(
                    f"[on_left] IGNORED (grace {elapsed:.1f}s) chat={chat_id}"
                )
                return
            LOGGER(__name__).warning(f"[on_left] chat={chat_id}")
            _recently_joined.pop(chat_id, None)
            try:
                await self.stop_stream(chat_id)
            except Exception as e:
                LOGGER(__name__).error(f"stop_stream error: {e}")

        # ============================================================
        #  STREAM END → play next track
        # ============================================================
        @self.one.on_stream_end()
        @self.two.on_stream_end()
        @self.three.on_stream_end()
        @self.four.on_stream_end()
        @self.five.on_stream_end()
        async def stream_end_handler1(client, update: Update):
            if not isinstance(update, StreamAudioEnded):
                return
            await asyncio.sleep(1)
            try:
                await self.change_stream(client, update.chat_id)
            except Exception as e:
                LOGGER(__name__).error(f"change_stream error: {e}")


DevSp = Call()
