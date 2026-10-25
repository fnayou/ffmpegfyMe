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
        "output": "video1.mp4",
        "id": "video-1"
    }
]
```

The optional `id` is a public stable identifier and must not contain secrets.

### 2. Build the container

```bash
task docker:build
```

### 3. Run interactively

```bash
task ffmpegfy:run
```

### 4. Configure authentication (optional)

Protected sources may require HTTP header or cookie auth.

Supported source and HLS segment protocols are `HTTP`/`HTTPS`. FFmpeg runs with
`-protocol_whitelist http,https,tcp,tls,crypto`, so nested protocols are restricted.

Manifest example with auth env references (`in/stream-list.json`):

```json
[
    {
        "url": "https://cdn.example.com/video1.m3u8",
        "output": "video1.mp4",
        "id": "video-1",
        "headers": {
            "Authorization": "${API_TOKEN}"
        },
        "cookies": "${SESSION_COOKIE}"
    }
]
```

-   Env references must be exactly `${ENV_NAME}` (e.g. `${API_TOKEN}`, `${SESSION_COOKIE}`).
-   Values like `Bearer ${API_TOKEN}` are invalid; refs must be exact.
-   Credentials do not belong in the manifest; only `${ENV_NAME}` placeholders.

Header and cookie auth can serve playlists and segments.

Create a git-ignored `.env` with placeholder example values:

```bash
API_TOKEN=your-api-token-here
SESSION_COOKIE=your-session-cookie-here
```

Compose injects these values at runtime via `env_file`. No real secrets.

Credentials are redacted (shown as `[REDACTED]`) in CLI output, errors, FFmpeg diagnostics, progress, and summaries.

Limitation: local users/processes may inspect credential-bearing FFmpeg arguments while FFmpeg runs.

### FFmpeg inactivity timeout

Default inactivity timeout is 60 seconds without FFmpeg output; any output resets the inactivity timer.

Set positive seconds with `FFMPEG_INACTIVITY_TIMEOUT` in the git-ignored `.env`:

```bash
FFMPEG_INACTIVITY_TIMEOUT=120
```

Invalid, non-finite, zero, and negative values produce a clear error before batch processing.

A timeout counts as a failed attempt and follows the retry policy: initial attempt plus up to two retries.

There is no total-download time limit by default; a download can run longer while FFmpeg continues producing output.

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

## Tests

Run the Python test suite with branch coverage. See [CONTRIBUTING.md](CONTRIBUTING.md#tests-and-ci) for the local environment and commands.

GitHub Actions runs it on pull requests to `main` and pushes to `main`.

---

## Dependencies

-   Python 3.11+
-   `ffmpeg` installed in container
-   Docker + Compose plugin
-   Taskfile (https://taskfile.dev)

---

## Community

-   [Code of Conduct](CODE_OF_CONDUCT.md)
-   [Contributing](CONTRIBUTING.md)
-   [Security](SECURITY.md)
-   [Support](SUPPORT.md)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Author

```txt
Name: Aymen FNAYOU
GitHub: https://github.com/fnayou
```
