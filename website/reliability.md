# Reliability

## Retries

The app makes an initial attempt plus up to two retries. Backoff waits are 1.5–2.5 seconds before the first retry and 5–7 seconds before the second.

Inactivity timeouts and other FFmpeg download failures use this retry policy. Authentication configuration errors, FFmpeg process-start errors, and failures to move a completed output into place are not retried.

## Inactivity timeout

- Default inactivity timeout: 60 seconds.
- Any FFmpeg output resets the timer.
- Set `FFMPEG_INACTIVITY_TIMEOUT` in `.env` for Compose, or export it for direct local runs.
- Must be a finite positive number.

Invalid, non-finite, zero, and negative values produce a clear error before batch processing.

## No total-download cap

No total-download timeout is implemented.

## Progress and state

- Per-item progress lives under `progress/`.
- Legacy `last_index` state is detected and requires an explicit reset choice.

A successful item is skipped only when its saved state says success and the output
file still exists.

Existing outputs are never silently overwritten.

- Manual mode asks before overwrite.
- Automatic mode records a conflict/failure and continues.

See [Troubleshooting](troubleshooting.md).
