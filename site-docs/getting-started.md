# Getting Started

## Prerequisites

- Python 3.11+
- FFmpeg installed and available on `PATH`
- Docker Engine and Docker Compose (optional, for container use)

## Docker Compose

The project provides a Compose service named `ffmpegfy-me`.

```bash
docker compose build
docker compose up
```

The service mounts `in/`, `out/`, and `progress/`, and optionally loads a
git-ignored `.env` file for credentials.

## Direct local use

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python ffmpegfyMe.py
```

FFmpeg must be on `PATH`.

## Input, output, and progress

- Place the JSON manifest at `in/stream-list.json`.
- Outputs are written to `out/`.
- Per-item progress state is kept under `progress/`.

## Interactive prompts

ffmpegfyMe has no command-line argument parser and no command flags.

Use the interactive prompts to configure batches and overwrite behavior.

See [Manifest](manifest.md) for the input format.
