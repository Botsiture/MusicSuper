import asyncio
import os
import re
import time
from typing import Union, Dict, Tuple, Any, List
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

DOWNLOAD_DIR = "downloads"

# ============================================================
#  SUPERFAST SEARCH CACHE  (single fetch -> many reuse)
# ============================================================
_SEARCH_CACHE: Dict[str, Tuple[float, List[dict]]] = {}
_SEARCH_CACHE_TTL = 900       # 15 minutes
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
    """
    एक ही upstream fetch (limit=10) कैश होगा और track/details/slider
    सब उसी result को reuse करेंगे -> बहुत fast.
    """
    cached = _cache_get(query)
    if cached is not None:
        return cached[:limit]

    inflight = _INFLIGHT.get(query)
    if inflight is not None:
        full = await inflight
        return full[:limit]

    task = asyncio.ensure_future(_do_search(query, 10))
    _INFLIGHT[query] = task
    try:
        full = await task
    finally:
        _INFLIGHT.pop(query, None)
    return full[:limit]


def prefetch_search(query: str):
    """Background में cache warm करो (fire & forget)."""
    if not query or _cache_get(query) is not None or query in _INFLIGHT:
        return
    try:
        asyncio.ensure_future(_search(query, 10))
    except Exception:
        pass


# ============================================================
#  SHARED HTTP SESSION (faster downloads)
# ============================================================
_SESSION: aiohttp.ClientSession = None


async def _get_session() -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is None or _SESSION.closed:
        connector = aiohttp.TCPConnector(
            limit=50, ttl_dns_cache=300, force_close=False
        )
        _SESSION = aiohttp.ClientSession(connector=connector)
    return _SESSION


# ============================================================
#  DOWNLOAD HELPERS
# ============================================================
async def download_song(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    if not API_URL:
        return None

    params = {"url": video_id, "type": "audio"}
    if API_KEY:
        params["api_key"] = API_KEY

    try:
        session = await _get_session()
        async with session.get(
            f"{API_URL}/download",
            params=params,
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp:
            if resp.status != 200:
                return None
            with open(file_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(262144):
                    f.write(chunk)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None


async def download_video(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    if not API_URL:
        return None

    params = {"url": video_id, "type": "video"}
    if API_KEY:
        params["api_key"] = API_KEY

    try:
        session = await _get_session()
        async with session.get(
            f"{API_URL}/download",
            params=params,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as resp:
            if resp.status != 200:
                return None
            with open(file_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(262144):
                    f.write(chunk)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None


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
        ytdl_opts = {"quiet": True}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
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
