# ffmpegfyMe

**Download HTTP/HLS streams as MP4 or MKV — no transcoding.**

**ffmpegfyMe** is an interactive or batch Python wrapper around
[FFmpeg](https://ffmpeg.org/) for downloading HTTP and HTTPS media streams,
commonly HLS playlists, and saving them into local media files.

## Implemented capabilities

- Downloads HTTP/HTTPS media streams, commonly HLS (`.m3u8`) playlists.
- Copies the stream into an `.mp4` or `.mkv` container using FFmpeg stream copy
  (`-c copy`).
- Supports interactive or batch mode, progress tracking, retries, and saved state.

## Why use it

- One tool wraps the heavy lifting: playlist handling, retries, progress, and state.
- Stream copy means no transcoding step.
- Works with Docker or a local Python environment.

## Workflow at a glance

1. Add one or more JSON manifests to `in/`.
2. Run ffmpegfyMe and choose a manifest when prompted.
3. Choose an output directory or accept the `out/<manifest-name>/` default.

See [Getting Started](getting-started.md) for setup and
[Manifest](manifest.md) for the input format.

## MP4/MKV and stream copy

ffmpegfyMe does **not** transcode. FFmpeg uses stream copy (`-c copy`).

Success depends on the source streams being compatible with the chosen container.
An `.mp4` or `.mkv` output is required; unsupported codec or container combinations
fail and are reported per item.

See [Troubleshooting](troubleshooting.md) for common failures.

## Implemented today

Feature descriptions across this site and the README describe implemented behavior. Planned work is tracked in GitHub Issues and may not be available yet.
