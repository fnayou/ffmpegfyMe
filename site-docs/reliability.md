# Reliability

## Retries

The app makes an initial attempt plus up to two retries, with short backoff delays.

A timed-out attempt is retried under the same policy as other failures.

## Inactivity timeout

- Default inactivity timeout: 60 seconds.
- Any FFmpeg output resets the timer.
- Set with `FFMPEG_INACTIVITY_TIMEOUT`.
- Must be a finite positive number.

Invalid, non-finite, zero, and negative values produce a clear error before batch processing.

## No total-download cap

There is no total-download time limit by default.

## Progress and state

- Per-item progress lives under `progress/`.
- Legacy `last_index` state is detected and requires an explicit reset choice.

A successful item is skipped only when its saved state says success and the output
file still exists.

Existing outputs are never silently overwritten.

- Manual mode asks before overwrite.
- Automatic mode records a conflict/failure and continues.

See [Troubleshooting](troubleshooting.md).
