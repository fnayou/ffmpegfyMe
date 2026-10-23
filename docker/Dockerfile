# Dockerfile for ffmpegfyMe

FROM python:3.11-slim-bookworm

# Pinned Debian Bookworm FFmpeg.
# Package version: 7:5.1.9-0+deb12u1 (ships ffmpeg, ffplay and ffprobe)
# Source: https://packages.debian.org/bookworm/ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg=7:5.1.9-0+deb12u1 && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code only — no manifests, media, secrets, or state
COPY ffmpegfyMe.py ./

# Copy container smoke check
COPY docker/smoke-check.sh /app/docker/smoke-check.sh
RUN chmod +x /app/docker/smoke-check.sh

# Default command (overridden by docker-compose)
CMD ["python", "ffmpegfyMe.py"]
