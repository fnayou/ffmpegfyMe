# ffmpegfyMe

**ffmpegfyMe** is an interactive or batch Python wrapper around
[FFmpeg](https://ffmpeg.org/) for downloading HTTP and HTTPS media streams,
commonly HLS playlists, and saving them into local media files.

## What it does

- Downloads HTTP/HTTPS media streams, commonly HLS (`.m3u8`) playlists.
- Copies the stream into an `.mp4` or `.mkv` container using FFmpeg stream copy
  (`-c copy`).
- Supports interactive or batch mode, progress tracking, retries, and saved state.

## Why use it

- One tool wraps the heavy lifting: playlist handling, retries, progress, and state.
- Stream copy means no transcoding step.
- Works with Docker or a local Python environment.

## Workflow at a glance

1. Create a manifest at `in/stream-list.json`.
2. Run ffmpegfyMe.
3. Finished files appear in `out/`.

See [Getting Started](getting-started.md) for setup and
[Manifest](manifest.md) for the input format.

## MP4/MKV and stream copy

ffmpegfyMe does **not** transcode. FFmpeg uses stream copy (`-c copy`).

Success depends on the source streams being compatible with the chosen container.
An `.mp4` or `.mkv` output is required; unsupported codec or container combinations
fail and are reported per item.

See [Troubleshooting](troubleshooting.md) for common failures.
