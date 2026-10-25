# Manifest

The manifest is a JSON list of items. Each item requires `url` and `output`.

## Fields

| Field | Required | Notes |
|---|---|---|
| `url` | yes | HTTP(S) media URL, commonly an `.m3u8` playlist |
| `output` | yes | Output filename, not a path; must end in `.mp4` or `.mkv` |
| `id` | no | Optional stable identifier, subject to the format and length limit below |
| `headers` | no | Optional header names mapped to environment references |
| `cookies` | no | Optional single environment reference |

## Rules

- Unknown fields are rejected.
- Duplicate IDs are rejected.
- Duplicate output destinations are rejected (case-insensitive).
- Only HTTP and HTTPS URLs are allowed.
- Userinfo in URLs is rejected.
- Unsafe output paths are rejected.
- Output extensions other than MP4/MKV are rejected.
- Output is a filename, not a path.

## Processing limits

- Input URLs must use HTTP or HTTPS. Playlist segments may use HTTP, HTTPS, TCP, TLS, or crypto protocols.
- Subtitle and data streams are not copied. Media streams are copied without transcoding.
- Stable IDs must match `[A-Za-z0-9][A-Za-z0-9._-]*` and be no longer than 128 characters.
- Header names must be valid HTTP token names and unique without regard to case.

## Stable IDs

An explicit `id` must be safe and public.

Without an explicit `id`, identity is derived from the URL and output.

## Example

```json
[
    {
        "url": "https://cdn.example.com/video1.m3u8",
        "output": "video1.mp4",
        "id": "video-1"
    }
]
```

Use placeholder URLs and identifiers only.
