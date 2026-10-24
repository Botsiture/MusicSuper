FROM nikolaik/python-nodejs:python3.10-nodejs20

# System dependencies: ffmpeg + build tools + native libs for ntgcalls/py-tgcalls
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg git curl ca-certificates \
        build-essential pkg-config \
        libssl-dev libffi-dev \
        libjpeg-dev zlib1g-dev \
        libavformat-dev libavcodec-dev libavutil-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* /var/tmp/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.txt /app/requirements.txt

# Python deps: pehle requirements (aiohttp 3.14.x yahin se aayega), phir py-yt-search --no-deps,
# phir yt-dlp latest (YouTube changes ke liye)
RUN pip3 install --no-cache-dir -U pip setuptools wheel \
    && pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install --no-cache-dir --no-deps py-yt-search==0.8.0 \
    && pip3 install --no-cache-dir -U yt-dlp

COPY . /app/

RUN mkdir -p /app/downloads /app/playback /app/cache \
    && chmod +x /app/start || true

ENV MusicSp_API_URL="https://apisparrow.site" \
    DYNO="docker" \
    HOME="/app"

EXPOSE 8080

CMD ["bash", "start"]
