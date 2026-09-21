from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram import types

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


def _progress_bar(played, dur, width=13):
    try:
        played_sec = max(0, time_to_seconds(played))
        duration_sec = max(1, time_to_seconds(dur))
    except Exception:
        return None

    ratio = min(1.0, max(0.0, played_sec / duration_sec))
    pos = min(width - 1, int(round(ratio * (width - 1))))
    # Patla wala bar Heer jaisa
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
    
    # Progress text for standard fallback (Rich message uses its own progress block)
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

    rows.append(
        [
            InlineKeyboardButton(
                text="↶ Replay",
                callback_data=f"ADMIN Replay|{chat_id}",
            ),
            InlineKeyboardButton(
                text="Ⅱ Pause" if playing else "Resume",
                callback_data=f"ADMIN {'Pause' if playing else 'Resume'}|{chat_id}",
            ),
            InlineKeyboardButton(
                text="» Skip",
                callback_data=f"ADMIN Skip|{chat_id}",
            ),
        ]
    )

    queue_count = max(0, len(current) - 1)
    videoid = current[0].get("vidid", "") if current else ""
    rows.append(
        [
            InlineKeyboardButton(
                text=f"≡ Queue • {queue_count}",
                callback_data=f"GetQueued g|{videoid}",
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


def _convert_to_rich_buttons(buttons):
    """Standard InlineKeyboardButton ko Native RichMessageButtons mein convert karta hai."""
    rich_rows = []
    for row in buttons:
        rich_buttons = []
        for btn in row:
            if btn.callback_data:
                # Timer button blockquote ke andar dikhega uske liye skip the standard button mapping
                if btn.callback_data == "GetTimer":
                    continue
                rich_buttons.append(
                    types.RichMessageButton(
                        text=types.RichTextPlain(text=btn.text),
                        callback_data=btn.callback_data,
                        style="primary"
                    )
                )
            elif btn.url:
                rich_buttons.append(
                    types.RichMessageButton(
                        text=types.RichTextPlain(text=btn.text),
                        url=btn.url,
                        style="primary"
                    )
                )
        if rich_buttons:
            rich_rows.append(
                types.InputRichBlockButtons(
                    buttons=rich_buttons,
                    align="center"
                )
            )
    return rich_rows


async def refresh_player_markup(_, chat_id, playing=True):
    current = db.get(chat_id) or []

    if not current:
        return
    mystic = current[0].get("mystic")
    if not mystic:
        return

    track = current[0]
    played = seconds_to_min(track.get("played", 0))
    dur = track.get("dur", "00:00")

    try:
        buttons = stream_markup(_, chat_id, playing=playing)

        # 1. Rich message update path
        if hasattr(mystic, "edit_rich_message"):
            try:
                rich_button_rows = _convert_to_rich_buttons(buttons)
                saved_photo = track.get("photo")
                saved_caption = track.get("caption")

                new_blocks = []
                if saved_photo and saved_caption:
                    new_blocks.append(
                        types.InputRichBlockPhoto(
                            photo=saved_photo,
                            caption=types.RichTextPlain(text=saved_caption)
                        )
                    )

                bar = _progress_bar(played, dur)
                # Adding progress text cleanly as a separate text block
                new_blocks.append(
                    types.InputRichBlockProgressBar(
                        progress=0,  # Or logic to calc 0-100
                        text=types.RichTextPlain(text=f"{played}  {bar}  {dur}")
                    )
                )

                new_blocks.extend(rich_button_rows)

                await mystic.edit_rich_message(
                    rich_message=types.InputRichMessage(blocks=new_blocks)
                )
                return  # Success
            except Exception as rich_err:
                print(f"Rich edit failed, falling back: {rich_err}")

        # 2. Fallback if edit_rich_message isn't present
        await mystic.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        print(f"refresh_player_markup error: {e}")


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
