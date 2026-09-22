import asyncio
import os
import re
import shutil
import time
from typing import Union, Dict, Tuple, List
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from py_yt import VideosSearch, Playlist
import aiohttp
import config

API_URL = config.API_URL or os.environ.get("MusicSp_API_URL", "https://apisparrow.site")
if API_URL:
    API_URL = API_URL.rstrip("/")
API_KEY = config.API_KEY or os.environ.get("MusicSp_API_KEY", None)

# ============================================================
#  HEROKU-AWARE DOWNLOAD DIR
#  Heroku only /tmp is writable. Ephemeral per dyno cycle.
# ============================================================
IS_HEROKU = bool(os.environ.get("DYNO"))
if IS_HEROKU:
    DOWNLOAD_DIR = "/tmp/downloads"
else:
    DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ============================================================
#  SUPERFAST SEARCH CACHE
# ============================================================
_SEARCH_CACHE: Dict[str, Tuple[float, List[dict]]] = {}
_SEARCH_CACHE_TTL = 900
_SEARCH_CACHE_MAX = 600
_INFLIGHT: Dict[str, asyncio.Task] = {}


def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))


def _cache_get(key: str):
    entry = _SEARCH_CACHE.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > _SEARCH_CACHE_TTL:
        _SEARCH_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: List[dict]):
    _SEARCH_CACHE[key] = (time.time(), value)
    if len(_SEARCH_CACHE) > _SEARCH_CACHE_MAX:
        evict_n = max(1, _SEARCH_CACHE_MAX // 5)
        for k, _ in sorted(_SEARCH_CACHE.items(), key=lambda kv: kv[1][0])[:evict_n]:
            _SEARCH_CACHE.pop(k, None)


async def _do_search(query: str, limit: int = 10) -> List[dict]:
    vs = VideosSearch(query, limit=limit)
    res = await vs.next()
    result = (res or {}).get("result") or []
    _cache_set(query, result)
    return result


async def _search(query: str, limit: int = 1) -> List[dict]:
    cached = _cache_get(query)
    if cached is not None:
        return cached[:limit]

    inflight = _INFLIGHT.get(query)
    if inflight is not None:
        try:
            full = await inflight
            return full[:limit]
        except Exception:
            return []

    task = asyncio.ensure_future(_do_search(query, 10))
    _INFLIGHT[query] = task
    try:
        full = await task
    finally:
        _INFLIGHT.pop(query, None)
    return full[:limit]


def prefetch_search(query: str):
    """Background cache warm — fire & forget."""
    if not query or _cache_get(query) is not None or query in _INFLIGHT:
        return
    try:
        asyncio.ensure_future(_search(query, 10))
    except Exception:
        pass


# ============================================================
#  SHARED HTTP SESSION
# ============================================================
_SESSION: aiohttp.ClientSession = None


async def _get_session() -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is None or _SESSION.closed:
        connector = aiohttp.TCPConnector(
            limit=50,
            ttl_dns_cache=300,
            force_close=False,
            enable_cleanup_closed=True,
        )
        _SESSION = aiohttp.ClientSession(connector=connector)
    return _SESSION


# ============================================================
#  HELPERS
# ============================================================
def _vid_from_link(link: str) -> str:
    if "v=" in link:
        return link.split("v=")[-1].split("&")[0]
    if "youtu.be/" in link:
        return link.split("youtu.be/")[-1].split("?")[0]
    return link


def _is_valid_audio(path: str, min_size: int = 100 * 1024) -> bool:
    if not os.path.exists(path):
        return False
    size = os.path.getsize(path)
    if size < min_size:
        return False
    try:
        with open(path, "rb") as f:
            head = f.read(3)
        # ID3 tag or MP3 frame sync
        if head[:3] == b"ID3" or (len(head) >= 1 and head[0] == 0xFF):
            return True
        # Some APIs send raw frames without ID3
        return size >= min_size
    except Exception:
        return False


def _is_valid_video(path: str, min_size: int = 500 * 1024) -> bool:
    if not os.path.exists(path):
        return False
    return os.path.getsize(path) >= min_size


# ============================================================
#  DOWNLOAD WITH YT-DLP FALLBACK (HIGH QUALITY)
# ============================================================
def _yt_dlp_download_sync(video_id: str, audio: bool = True, hq: bool = True) -> str:
    """Blocking yt-dlp download. Runs in executor."""
    if audio:
        out_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192" if hq else "128",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "nocheckcertificate": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
        }
    else:
        out_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
        ydl_opts = {
            "format": "best[ext=mp4][height<=480]/best[height<=480]/best",
            "outtmpl": out_path,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "nocheckcertificate": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

    return out_path if os.path.exists(out_path) else None


async def download_song(link: str) -> str:
    video_id = _vid_from_link(link)
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")

    # Cache hit
    if _is_valid_audio(file_path):
        return file_path

    # ---- Try primary API (fast) ----
    if API_URL:
        params = {
            "url": video_id,
            "type": "audio",
            "quality": "high",     # API hint
            "bitrate": "192",
        }
        if API_KEY:
            params["api_key"] = API_KEY

        try:
            session = await _get_session()
            async with session.get(
                f"{API_URL}/download",
                params=params,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(262144):
                            f.write(chunk)
                    if _is_valid_audio(file_path):
                        return file_path
                    # invalid → delete
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
        except Exception:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    # ---- Fallback: yt-dlp HQ (slow but guaranteed) ----
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, _yt_dlp_download_sync, video_id, True, True
        )
        if result and _is_valid_audio(result):
            return result
    except Exception:
        pass

    return None


async def download_video(link: str) -> str:
    video_id = _vid_from_link(link)
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")

    if _is_valid_video(file_path):
        return file_path

    # ---- Try primary API ----
    if API_URL:
        params = {"url": video_id, "type": "video", "quality": "high"}
        if API_KEY:
            params["api_key"] = API_KEY

        try:
            session = await _get_session()
            async with session.get(
                f"{API_URL}/download",
                params=params,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(262144):
                            f.write(chunk)
                    if _is_valid_video(file_path):
                        return file_path
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
        except Exception:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    # ---- Fallback: yt-dlp ----
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, _yt_dlp_download_sync, video_id, False, True
        )
        if result and _is_valid_video(result):
            return result
    except Exception:
        pass

    return None


# ============================================================
#  HEROKU CACHE CLEANUP (24h old files delete)
# ============================================================
async def cleanup_downloads(max_age_hours: int = 12, max_size_mb: int = 500):
    """Background task: keeps /tmp/downloads from filling up."""
    while True:
        try:
            now = time.time()
            max_age = max_age_hours * 3600
            total = 0
            files = []
            for f in os.listdir(DOWNLOAD_DIR):
                p = os.path.join(DOWNLOAD_DIR, f)
                if not os.path.isfile(p):
                    continue
                st = os.stat(p)
                if now - st.st_mtime > max_age:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                else:
                    total += st.st_size
                    files.append((p, st.st_mtime))

            # If still over size limit, delete oldest
            limit_bytes = max_size_mb * 1024 * 1024
            if total > limit_bytes:
                files.sort(key=lambda x: x[1])
                for p, _ in files:
                    try:
                        os.remove(p)
                        total -= os.path.getsize(p) if os.path.exists(p) else 0
                    except Exception:
                        pass
                    if total <= limit_bytes:
                        break
        except Exception:
            pass
        await asyncio.sleep(1800)   # every 30 min


# ============================================================
#  MAIN API CLASS
# ============================================================
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        if text:
                            return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await _search(link, 1)
        if not result:
            return "", "0:00", 0, "", ""
        r = result[0]
        title = r.get("title", "")
        duration_min = r.get("duration", "0:00")
        thumbnails = r.get("thumbnails", [])
        thumbnail = thumbnails[0]["url"].split("?")[0] if thumbnails else ""
        vidid = r.get("id", "")
        duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await _search(link, 1)
        return result[0].get("title", "") if result else ""

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await _search(link, 1)
        return result[0].get("duration", "0:00") if result else "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await _search(link, 1)
        if not result:
            return ""
        thumbnails = result[0].get("thumbnails", [])
        return thumbnails[0]["url"].split("?")[0] if thumbnails else ""

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            plist = await Playlist.get(link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data:
                continue
            vid = data.get("id")
            if not vid:
                continue
            ids.append(vid)
        return ids

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await _search(link, 1)
        if not result:
            return {}, ""
        r = result[0]
        title = r.get("title", "")
        duration_min = r.get("duration", "0:00")
        vidid = r.get("id", "")
        yturl = r.get("link", "")
        thumbnails = r.get("thumbnails", [])
        thumbnail = thumbnails[0]["url"].split("?")[0] if thumbnails else ""
        track_details = {
            "title": title,
            "link": yturl,
            "vidid": vidid,
            "duration_min": duration_min,
            "thumb": thumbnail,
        }
        return track_details, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {"quiet": True, "no_warnings": True}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        formats_available = []
        try:
            with ydl:
                r = ydl.extract_info(link, download=False)
                for format in r.get("formats", []):
                    try:
                        if "dash" not in str(format["format"]).lower():
                            formats_available.append(
                                {
                                    "format": format["format"],
                                    "filesize": format.get("filesize"),
                                    "format_id": format["format_id"],
                                    "ext": format["ext"],
                                    "format_note": format["format_note"],
                                    "yturl": link,
                                }
                            )
                    except Exception:
                        continue
        except Exception:
            pass
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await _search(link, 10)
        if not result or query_type >= len(result):
            return "", "0:00", "", ""
        r = result[query_type]
        title = r.get("title", "")
        duration_min = r.get("duration", "0:00")
        vidid = r.get("id", "")
        thumbnails = r.get("thumbnails", [])
        thumbnail = thumbnails[0]["url"].split("?")[0] if thumbnails else ""
        return title, duration_min, thumbnail, vidid

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        try:
            if video:
                downloaded_file = await download_video(link)
            else:
                downloaded_file = await download_song(link)
            if downloaded_file:
                return downloaded_file, True
            return None, False
        except Exception:
            return None, False


YouTube = YouTubeAPI()
