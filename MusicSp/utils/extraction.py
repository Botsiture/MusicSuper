from pyrogram.enums import MessageEntityType
from pyrogram.types import Message, User

from MusicSp import app


async def extract_user(m: Message) -> User:
    # Reply based
    if m.reply_to_message:
        return m.reply_to_message.from_user

    if not m.text or not m.entities:
        return None

    entities = m.entities

    # Skip /command entity
    if m.text.startswith("/"):
        if len(entities) < 2:
            return None
        msg_entities = entities[1]
    else:
        msg_entities = entities[0]

    # Text mention (@user via entity)
    if msg_entities.type == MessageEntityType.TEXT_MENTION:
        return msg_entities.user

    # Numeric ID or username from command args
    if not m.command or len(m.command) < 2:
        return None

    arg = m.command[1]
    return await app.get_users(int(arg) if arg.isdecimal() else arg)
