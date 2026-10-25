# Authentication

Protected sources may require HTTP header or cookie auth.

## Environment references

Auth values use exact environment references such as `${API_TOKEN}`.

```json
{
    "headers": {
        "Authorization": "${API_TOKEN}"
    },
    "cookies": "${SESSION_COOKIE}"
}
```

A prefix such as `Bearer ${API_TOKEN}` is invalid. References must be exact.

Header values map header names to references.

`cookies` takes one reference.

## Configuration

Compose loads a git-ignored `.env` file and injects values via `env_file`.

A direct local Python run needs the variables exported in the process environment.

## Secrets

- No real secrets in examples.
- Use placeholder values only.
- Credentials do not belong in the manifest; only `${ENV_NAME}` placeholders.

## Privacy

- The CLI redacts HTTP(S) URLs and cookie values from displayed FFmpeg output and error lines. Header values may appear if FFmpeg echoes them.
- Progress state stores item status/output and an identity key, not raw manifest
  URLs or credentials.

## Caveats

- Signed URLs remain in plaintext in the manifest file. Protect that file and avoid sharing or committing URLs that contain credentials.
- Local processes may inspect credential-bearing FFmpeg arguments while FFmpeg runs.

See [Reliability](reliability.md) for state and retries.
