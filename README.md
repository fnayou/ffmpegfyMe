# ffmpegfyMe

**ffmpegfyMe** is a Dockerized Python CLI tool for downloading streaming media (e.g. `.m3u8`) using `ffmpeg`.  
It offers interactive or batch downloading, progress tracking, retry logic, and state persistence.

---

## Features

-   Stream download using `ffmpeg`
-   Manual or automatic batch mode
-   Progress tracking per batch
-   Retry logic and skip for already-downloaded files
-   Persistent state across runs
-   Docker + Taskfile support
-   Input via versioned JSON list file

---

## Project Structure

```bash
ffmpegfyMe/
├── ffmpegfyMe.py              # Main CLI script
├── docker/
│   └── Dockerfile             # ffmpeg + Python base image
├── compose.yml                # Compose service: ffmpegfy-me
├── Taskfile.yml               # Task runner integration
├── .gitignore
├── requirements.txt
├── in/
│   ├── stream-list.json       # Versioned input list
│   └── .gitkeep
├── out/
│   └── .gitkeep
└── progress/
    └── .gitkeep
```

---

## Usage

### 1. Prepare your input file

Example: `in/stream-list.json`

```json
[
    {
        "url": "https://cdn.example.com/video1.m3u8",
        "output": "video1.mp4"
    }
]
```

### 2. Build the container

```bash
task docker:build
```

### 3. Run interactively

```bash
task ffmpegfy:run
```

---

## Docker

-   Base image: `python:3.11-slim-bookworm`
-   FFmpeg pinned to Debian Bookworm package `7:5.1.9-0+deb12u1` (ffmpeg + ffprobe report `5.1.9`)
-   Source: <https://packages.debian.org/bookworm/ffmpeg>

### Runtime data & secrets

-   Image contains code only — no Git metadata, manifests, credentials, media, output, or progress state.
-   Manifests (`in/`), credentials (`.env`), outputs (`out/`), progress state (`progress/`) are supplied at runtime via bind mounts / env file.

```bash
task docker:build
task docker:smoke
task ffmpegfy:run
```

-   Secrets live in `.env` (git-ignored) and are injected via `env_file` at runtime only.

---

## Dependencies

-   Python 3.11+
-   `ffmpeg` installed in container
-   Docker + Compose plugin
-   Taskfile (https://taskfile.dev)

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Author

```txt
Name: Aymen FNAYOU
GitHub: https://github.com/fnayou
```
