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
