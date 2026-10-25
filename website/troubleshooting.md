# Troubleshooting

## Missing FFmpeg

Check FFmpeg is installed and on `PATH`.

```bash
ffmpeg -version
```

## Invalid manifest, URL, or output

Check JSON validity, required fields, HTTP(S) URLs, output extension, and filename-only output rule.

## Missing auth environment values

For Compose, check that required `${ENV_NAME}` values are present in `.env`. For direct local Python runs, export each variable in the shell before starting the app; local Python use does not load `.env`.

## Output conflicts

Existing outputs are never silently overwritten.

Manual mode asks before overwrite. Automatic mode records a conflict/failure and continues.

## Inactivity timeouts

Default is 60 seconds. Any FFmpeg output resets it.

Set `FFMPEG_INACTIVITY_TIMEOUT` to a finite positive number in `.env` for Compose, or export it for direct local runs.

## Unsupported codecs/container combinations

ffmpegfyMe does not transcode. Stream copy (`-c copy`) requires source and container compatibility.

## Saved or legacy progress

Check `progress/` state. Legacy `last_index` state requires an explicit reset choice.

See [Reliability](reliability.md).
