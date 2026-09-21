# ATLEAST GIVE CREDITS IF YOU STEALING :(((((((((((((((((((((((((((((((((((((
# ELSE NO FURTHER PUBLIC THUMBNAIL UPDATES

import logging
import os
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from py_yt import VideosSearch

import config

logging.basicConfig(level=logging.INFO)

def changeImageSize(maxWidth, maxHeight, image):
    widthRatio = maxWidth / image.size[0]
    heightRatio = maxHeight / image.size[1]
    newWidth = int(widthRatio * image.size[0])
    newHeight = int(heightRatio * image.size[1])
    newImage = image.resize((newWidth, newHeight))
    return newImage

def truncate(text):
    list_words = text.split(" ")
    text1 = ""
    text2 = ""
    for i in list_words:
        if len(text1) + len(i) < 30:
            text1 += " " + i
        elif len(text2) + len(i) < 30:
            text2 += " " + i
    return [text1.strip(), text2.strip()]

async def gen_thumb(videoid: str):
    if not videoid or str(videoid).strip().lower() in ("none", "", "null"):
        return config.STREAM_IMG_URL
    try:
        os.makedirs("cache", exist_ok=True)
        background_path = f"cache/{videoid}_v4.png"
        
        if os.path.isfile(background_path):
            return background_path

        # 1. Fetch Video Details
        url = f"https://www.youtube.com/watch?v={videoid}"
        results = VideosSearch(url, limit=1)
        res_data = await results.next()
        
        thumbnail = None
        title = "Unknown Title"
        duration = "00:00"
        channel = "Unknown Artist"
        
        if res_data and "result" in res_data and len(res_data["result"]) > 0:
            result = res_data["result"][0]
            title = result.get("title", "Unknown Title")
            duration = result.get("duration", "00:00")
            channel = result.get("channel", {}).get("name", "Unknown Artist")
            thumbnail_data = result.get("thumbnails")
            if thumbnail_data:
                thumbnail = thumbnail_data[-1]["url"].split("?")[0]

        if not thumbnail:
            return config.STREAM_IMG_URL

        # 2. Download Thumbnail
        filepath = f"cache/thumb{videoid}.png"
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    async with aiofiles.open(filepath, mode="wb") as f:
                        await f.write(await resp.read())

        if not os.path.exists(filepath):
            return config.STREAM_IMG_URL

        # 3. Process Image
        youtube = Image.open(filepath).convert("RGBA")
        
        # A. Create Blurred Background
        background = youtube.copy()
        background = changeImageSize(1280, 720, background)
        background = background.filter(ImageFilter.GaussianBlur(20))
        
        # B. Make Center Image with Smooth Curved Corners
        yt_w, yt_h = 840, 470
        youtube_resized = changeImageSize(yt_w, yt_h, youtube)
        
        # Mask for curved corners
        mask = Image.new("L", (yt_w, yt_h), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([(0, 0), (yt_w, yt_h)], radius=35, fill=255) # radius=35 gives a smooth curve
        
        # Paste curved image exactly in the top-center
        x_offset = (1280 - yt_w) // 2
        y_offset = 50
        background.paste(youtube_resized, (x_offset, y_offset), mask)
        
        # C. Draw UI (Progress Bar & Text)
        draw = ImageDraw.Draw(background)
        
        # Load Fonts (Use defaults if assets missing, but recommend uploading Arial/Roboto)
        try:
            font_title = ImageFont.truetype("assets/font.ttf", 36)
            font_channel = ImageFont.truetype("assets/font.ttf", 26)
            font_dur = ImageFont.truetype("assets/font.ttf", 24)
        except:
            font_title = ImageFont.load_default()
            font_channel = ImageFont.load_default()
            font_dur = ImageFont.load_default()
        
        # Draw Progress Bar
        bar_x1 = 220
        bar_x2 = 1060
        bar_y = 620
        
        # Background grey line
        draw.line([(bar_x1, bar_y), (bar_x2, bar_y)], fill="#555555", width=8)
        # White filled progress (approx 30%)
        draw.line([(bar_x1, bar_y), (450, bar_y)], fill="white", width=8)
        # Progress Dot (Circle)
        draw.ellipse([(440, bar_y - 10), (460, bar_y + 10)], fill="white")
        
        # Draw Timestamps
        draw.text((bar_x1, bar_y + 15), "0:00", fill="white", font=font_dur)
        # Align duration to the right
        dur_w = draw.textlength(duration, font=font_dur) if hasattr(draw, 'textlength') else 50
        draw.text((bar_x2 - dur_w, bar_y + 15), duration, fill="white", font=font_dur)
        
        # Draw Title & Channel Name
        titles = truncate(title)
        draw.text((bar_x1, 540), titles[0], fill="white", font=font_title)
        draw.text((bar_x1, 580), channel, fill="#cccccc", font=font_channel)
        
        final_image = background.convert("RGB")
            
        try:
            os.remove(filepath)
        except Exception:
            pass
            
        final_image.save(background_path)
        return background_path

    except Exception as e:
        logging.error(f"Error generating thumbnail for video {videoid}: {e}")
        return config.STREAM_IMG_URL
