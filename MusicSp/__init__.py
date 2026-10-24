import os
import sys

# ✅ 0. Fix GitPython on Heroku: runtime par `git` executable available nahi hota.
#    Ye env var `import git` se PEHLE set hona chahiye, warna process crash karega.
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

import asyncio

# ✅ 1. Install uvloop (if available) BEFORE setting the event loop
if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
    except Exception:
        pass

# ✅ 2. Create and set an active event loop in MainThread for PyTgCalls sync compatibility
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
else:
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

# ✅ 3. Ensure pytgcalls is importable across all environments (Heroku, VPS, Containers)
try:
    import pytgcalls
except ModuleNotFoundError:
    import subprocess
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "py-tgcalls==0.9.7"],
            check=False,
        )
        import pytgcalls
    except Exception:
        pass

# ✅ 4. Apply PyTgCalls MTProto compatibility patches
import MusicSp.core.patch

# --- Original bot imports ---
from MusicSp.core.bot import DevSp
from MusicSp.core.dir import dirr
from MusicSp.core.git import git
from MusicSp.core.userbot import Userbot
from MusicSp.misc import dbb, heroku

from MusicSp.logging import LOGGER

# --- Initialization calls ---
dirr()
git()
dbb()
heroku()

# --- Create bot & userbot instances ---
app = DevSp()
userbot = Userbot()

# --- Platform imports ---
from MusicSp.platforms import *

Apple = AppleAPI()
Carbon = CarbonAPI()
SoundCloud = SoundAPI()
Spotify = SpotifyAPI()
Resso = RessoAPI()
Telegram = TeleAPI()
YouTube = YouTubeAPI()
