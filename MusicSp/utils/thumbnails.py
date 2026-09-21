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
        
        # Make sure this path matches where you upload your template
        bg_path = "assets/custom_bg.png" 
        
        if os.path.exists(bg_path):
            # A. Custom Template Logic
            background = Image.open(bg_path).convert("RGBA")
            background = background.resize((1280, 720))
            
            # Resize original YT thumbnail to fit inside the template's screen
            yt_w, yt_h = 760, 430
            youtube = youtube.resize((yt_w, yt_h))
            
            # Create rounded corners for the YT thumbnail
            mask = Image.new("L", (yt_w, yt_h), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle([(0, 0), (yt_w, yt_h)], radius=20, fill=255)
            
            # Paste the YT thumbnail onto your background template
            # Coordinates (X=260, Y=60) - You can adjust these to perfectly center it inside your frame
            background.paste(youtube, (260, 60), mask)
            
            # B. Draw Dynamic Text
            draw = ImageDraw.Draw(background)
            
            try:
                # Make sure you upload a font file in the assets folder
                font_title = ImageFont.truetype("assets/font.ttf", 34)
                font_channel = ImageFont.truetype("assets/font.ttf", 26)
                font_dur = ImageFont.truetype("assets/font.ttf", 22)
            except:
                font_title = ImageFont.load_default()
                font_channel = ImageFont.load_default()
                font_dur = ImageFont.load_default()
            
            # Draw Title
            titles = truncate(title)
            # Coordinates (X=320, Y=520) - Adjust based on your text area position
            draw.text((320, 520), titles[0], fill="white", font=font_title)
            if titles[1]:
                draw.text((320, 560), titles[1], fill="white", font=font_title)
                
            # Draw Artist/Channel
            draw.text((320, 610), channel, fill="#b3b3b3", font=font_channel)
            
            # Draw Duration (Left & Right of Progress Bar)
            draw.text((940, 645), duration, fill="white", font=font_dur)
            draw.text((320, 645), "0:00", fill="white", font=font_dur)
            
            final_image = background.convert("RGB")
        else:
            # Fallback if custom_bg.png is missing (Blurs the thumbnail to avoid crashes)
            background = youtube.copy()
            background = changeImageSize(1280, 720, background)
            background = background.filter(ImageFilter.GaussianBlur(15))
            youtube_resized = changeImageSize(840, 470, youtube)
            x = (1280 - youtube_resized.width) // 2
            y = (720 - youtube_resized.height) // 2
            background.paste(youtube_resized, (x, y))
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
