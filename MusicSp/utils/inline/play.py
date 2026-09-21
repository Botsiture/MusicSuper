import math

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from MusicSp.misc import db
from MusicSp.utils.formatters import time_to_seconds, seconds_to_min


def track_markup(_, videoid, user_id, channel, fplay):
    buttons = [
        [
            InlineKeyboardButton(
                text=_["P_B_1"],
                callback_data=f"MusicStream {videoid}|{user_id}|a|{channel}|{fplay}",
            ),
            InlineKeyboardButton(
                text=_["P_B_2"],
                callback_data=f"MusicStream {videoid}|{user_id}|v|{channel}|{fplay}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {videoid}|{user_id}",
            )
        ],
    ]
    return buttons


def _progress_bar(played, dur, width=15):
    try:
        played_sec = max(0, time_to_seconds(played))
        duration_sec = max(1, time_to_seconds(dur))
    except Exception:
        return None

    ratio = min(1.0, max(0.0, played_sec / duration_sec))
    pos = min(width - 1, int(round(ratio * (width - 1))))

    # Heer image jaisa patla progress bar (─)
    return "─" * pos + "●" + "─" * (width - pos - 1)


def _player_markup(_, chat_id, playing=True, played=None, dur=None):
    current = db.get(chat_id) or []

    if current:
        track = current[0]
        if played is None:
            played = seconds_to_min(track.get("played", 0))
        if dur is None:
            dur = track.get("dur")

    rows = []

    # Progress bar (Optional: Agar aap chahte hain ki buttons me bhi progress bar dikhe)
    bar = _progress_bar(played, dur) if played is not None and dur else None

    if bar:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{played}  {bar}  {dur}",
                    callback_data="GetTimer"
                )
            ]
        )

    # Main player controls
    rows.append(
        [
            InlineKeyboardButton(
                text="↶ Replay",
                callback_data=f"ADMIN Replay|{chat_id}",
            ),
            InlineKeyboardButton(
                text="Ⅱ Pause" if playing else "▶ Resume",
                callback_data=f"ADMIN {'Pause' if playing else 'Resume'}|{chat_id}",
            ),
            InlineKeyboardButton(
                text="» Skip",
                callback_data=f"ADMIN Skip|{chat_id}",
            ),
        ]
    )

    # Queue button
    queue_count = max(0, len(current) - 1)
    videoid = current[0].get("vidid", "") if current else ""

    rows.append(
        [
            InlineKeyboardButton(
                text=f"≡ Queue • {queue_count}",
                callback_data=f"GetQueuedg|{videoid}",
            )
        ]
    )

    return rows


def stream_markup_timer(_, chat_id, played, dur):
    return _player_markup(
        _,
        chat_id,
        playing=True,
        played=played,
        dur=dur,
    )


def stream_markup(_, chat_id, playing=True):
    return _player_markup(
        _,
        chat_id,
        playing=playing,
    )


async def refresh_player_markup(_, chat_id, playing=True):
    current = db.get(chat_id) or []

    if not current:
        return

    mystic = current[0].get("mystic")
    if not mystic:
        return

    try:
        buttons = stream_markup(
            _,
            chat_id,
            playing=playing,
        )

        await mystic.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception:
        pass


def playlist_markup(_, videoid, user_id, ptype, channel, fplay):
    buttons = [
        [
            InlineKeyboardButton(
                text=_["P_B_1"],
                callback_data=f"DevSpPlaylists {videoid}|{user_id}|{ptype}|a|{channel}|{fplay}",
            ),
            InlineKeyboardButton(
                text=_["P_B_2"],
                callback_data=f"DevSpPlaylists {videoid}|{user_id}|{ptype}|v|{channel}|{fplay}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {videoid}|{user_id}",
            ),
        ],
    ]
    return buttons


def livestream_markup(_, videoid, user_id, mode, channel, fplay):
    buttons = [
        [
            InlineKeyboardButton(
                text=_["P_B_3"],
                callback_data=f"LiveStream {videoid}|{user_id}|{mode}|{channel}|{fplay}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {videoid}|{user_id}",
            ),
        ],
    ]
    return buttons


def slider_markup(_, videoid, user_id, query, query_type, channel, fplay):
    query = f"{query[:20]}"
    buttons = [
        [
            InlineKeyboardButton(
                text=_["P_B_1"],
                callback_data=f"MusicStream {videoid}|{user_id}|a|{channel}|{fplay}",
            ),
            InlineKeyboardButton(
                text=_["P_B_2"],
                callback_data=f"MusicStream {videoid}|{user_id}|v|{channel}|{fplay}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="◁",
                callback_data=f"slider B|{query_type}|{query}|{user_id}|{channel}|{fplay}",
            ),
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {query}|{user_id}",
            ),
            InlineKeyboardButton(
                text="▷",
                callback_data=f"slider F|{query_type}|{query}|{user_id}|{channel}|{fplay}",
            ),
        ],
    ]
    return buttons
