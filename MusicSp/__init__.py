import os
import sys

# ✅ 0. GitPython fix (Heroku par `git` runtime par nahi hota)
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

# ✅ 0.1 Node.js fix (pytgcalls ke liye zaroori)
_venv_bin = os.path.dirname(sys.executable)
os.environ["PATH"] = _venv_bin + os.pathsep + os.environ.get("PATH", "")

# ✅ 0.2 FFmpeg fix (pytgcalls ko ffmpeg + ffprobe chahiye)
try:
    import static_ffmpeg
    # Ye line ffmpeg aur ffprobe binaries ko PATH mein add kar deti hai.
    # Agar pehle se available hain to skip kar deti hai (weak=True).
    static_ffmpeg.add_paths(weak=True)
except Exception:
    # Agar static-ffmpeg fail ho jaye to bhi bot crash na ho
    pass

import asyncio

# ✅ 1. uvloop install (if available) BEFORE setting event loop
if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
    except Exception:
        pass

# ✅ 2. Create and set active event loop for PyTgCalls sync compatibility
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
else:
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

# ✅ 3. Ensure pytgcalls importable (fallback)
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

# ✅ 4. PyTgCalls MTProto compatibility patches
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
