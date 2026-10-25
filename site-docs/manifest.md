# Manifest

The manifest is a JSON list of items. Each item requires `url` and `output`.

## Fields

| Field | Required | Optional | Notes |
|---|---|---|---|
| `url` | yes | no | HTTP(S) media URL, commonly an `.m3u8` playlist |
| `output` | yes | no | Output filename, not a path; must end in `.mp4` or `.mkv` |
| `id` | no | no | Safe, public stable identifier |
| `headers` | no | no | Header references, e.g. auth headers |
| `cookies` | no | no | Cookie reference |

## Rules

- Unknown fields are rejected.
- Duplicate IDs are rejected.
- Duplicate output destinations are rejected (case-insensitive).
- Only HTTP and HTTPS URLs are allowed.
- Userinfo in URLs is rejected.
- Unsafe output paths are rejected.
- Output extensions other than MP4/MKV are rejected.
- Output is a filename, not a path.

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
