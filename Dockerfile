FROM nikolaik/python-nodejs:python3.10-nodejs20

# ============================================================
#  SYSTEM DEPENDENCIES (FFmpeg + build essentials)
# ============================================================
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        curl \
        ca-certificates \
        build-essential \
        libssl-dev \
        libffi-dev \
        libjpeg-dev \
        zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* /var/tmp/*

# ============================================================
#  PYTHON ENV (faster, cleaner)
# ============================================================
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# ============================================================
#  WORKDIR
# ============================================================
WORKDIR /app

# ============================================================
#  INSTALL PYTHON DEPS FIRST  (Docker layer caching)
# ============================================================
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -U pip setuptools wheel \
    && pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install --no-cache-dir -U yt-dlp

# ============================================================
#  COPY APP  (after deps so cache is reused)
# ============================================================
COPY . /app/

# ============================================================
#  CREATE DOWNLOAD DIR + FIX PERMISSIONS
# ============================================================
RUN mkdir -p /app/downloads /app/playback /app/cache \
    && chmod +x /app/start || true

# ============================================================
#  HEROKU COMPATIBILITY
#  Heroku sets $PORT and expects the app to bind to it.
#  Also, Heroku dynos run as non-root; /tmp is writable.
# ============================================================
ENV MusicSp_API_URL="https://apisparrow.site" \
    DYNO="docker" \
    HOME="/app"

# ============================================================
#  EXPOSE PORT (Heroku needs this)
# ============================================================
EXPOSE 8080

# ============================================================
#  START
# ============================================================
CMD ["bash", "start"]
