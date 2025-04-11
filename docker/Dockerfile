# Dockerfile for ffmpegfyMe

FROM python:3.11-slim

# Install ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy everything into the container
COPY . /app

# Install dependencies (if any in requirements.txt)
RUN pip install --no-cache-dir -r requirements.txt

# Default command (overridden by docker-compose)
CMD ["python", "ffmpegfyMe.py"]
