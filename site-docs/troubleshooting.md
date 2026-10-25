# Troubleshooting

## Missing FFmpeg

Check FFmpeg is installed and on `PATH`.

```bash
ffmpeg -version
```

## Invalid manifest, URL, or output

Check JSON validity, required fields, HTTP(S) URLs, output extension, and filename-only output rule.

## Missing auth environment values

Check that required `${ENV_NAME}` references are exported or present in `.env`.

## Output conflicts

Existing outputs are never silently overwritten.

Manual mode asks before overwrite. Automatic mode records a conflict/failure and continues.

## Inactivity timeouts

Default is 60 seconds. Any FFmpeg output resets it.

Set `FFMPEG_INACTIVITY_TIMEOUT` to a finite positive number.

## Unsupported codecs/container combinations

ffmpegfyMe does not transcode. Stream copy (`-c copy`) requires source and container compatibility.

## Saved or legacy progress

Check `progress/` state. Legacy `last_index` state requires an explicit reset choice.

See [Reliability](reliability.md).
