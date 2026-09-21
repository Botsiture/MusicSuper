from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.raw import types as raw_types
from pyrogram.types import InputRichMessage

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


def _progress_bar(played, dur, width=12):
    try:
        played_sec = max(0, time_to_seconds(played))
        duration_sec = max(1, time_to_seconds(dur))
    except Exception:
        return None

    ratio = min(1.0, max(0.0, played_sec / duration_sec))
    pos = min(width - 1, int(round(ratio * (width - 1))))

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
                text="Ⅱ Pause" if playing else "▶ Resume",
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


def _convert_to_rich_buttons(buttons):
    """Standard InlineKeyboardButton ko PageBlockButtonRow mein convert karta hai."""
    button_rows = []
    for row in buttons:
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
    return button_rows


async def refresh_player_markup(_, chat_id, playing=True):
    current = db.get(chat_id) or []

    if not current:
        return

    mystic = current[0].get("mystic")
    if not mystic:
        return

    # Progress bar ke liye current track ka data nikalo
    track = current[0]
    played = seconds_to_min(track.get("played", 0))
    dur = track.get("dur", "00:00")

    try:
        buttons = stream_markup(
            _,
            chat_id,
            playing=playing,
        )

        # 1. Rich message ke liye try karo
        try:
            rich_button_rows = _convert_to_rich_buttons(buttons)
            
            # 🔥 Photo aur Caption db se nikalo (stream.py mein save kiye gaye hain)
            saved_photo = track.get("photo")
            saved_caption = track.get("caption")
            
            new_blocks = []
            
            # Agar photo aur caption saved hain, toh poora structure wapas banao
            if saved_photo and saved_caption:
                # Photo ko upload karo (kyunki edit ke liye file_id chahiye)
                temp_msg = await mystic.client.send_photo(chat_id=mystic.chat.id, photo=saved_photo)
                photo_file_id = temp_msg.photo.file_id
                await temp_msg.delete()
                
                new_blocks.append(
                    raw_types.PageBlockPhoto(
                        photo_id=photo_file_id,
                        caption=raw_types.PageCaption(
                            text=raw_types.TextRich(text=saved_caption)
                        )
                    )
                )
            
            # Progress bar block
            new_blocks.append(
                raw_types.PageBlockProgressBar(
                    progress=0, # 0 to 100 (Agar aapko dynamic chahiye toh yahan calculation daalein)
                    text=raw_types.TextPlain(text=f"{played} / {dur}")
                )
            )
            
            # Buttons add karo
            new_blocks.extend(rich_button_rows)

            await mystic.edit_rich_message(
                rich_message=InputRichMessage(blocks=new_blocks)
            )
            return  # Agar rich message update ho gaya, toh yahin ruk jao

        except Exception as rich_err:
            # Agar rich message update fail hota hai, toh fallback (standard buttons)
            print(f"Rich edit failed, falling back to standard: {rich_err}")

        # 2. Fallback: Standard buttons update karo
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
