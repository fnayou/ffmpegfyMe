import unittest

import ffmpegfyMe


class ResolveRequestAuthTests(unittest.TestCase):
    def test_no_auth_returns_empty_headers_and_none_cookies(self) -> None:
        resolved_headers, resolved_cookies = ffmpegfyMe.resolve_request_auth(
            {"url": "https://cdn.example.com/video1.m3u8", "output": "video1.mp4"}
        )
        self.assertEqual(resolved_headers, {})
        self.assertIsNone(resolved_cookies)

    def test_resolves_multiple_headers_and_cookie_from_env_references(self) -> None:
        item = {
            "url": "https://cdn.example.com/video1.m3u8",
            "output": "video1.mp4",
            "headers": {
                "Authorization": "${API_TOKEN}",
                "X-Custom-Header": "${CUSTOM_TOKEN}",
                "User-Agent": "${UA_NAME}",
            },
            "cookies": "${SESSION_ID}",
        }
        resolved_headers, resolved_cookies = ffmpegfyMe.resolve_request_auth(
            item,
            environment={
                "API_TOKEN": "tok",
                "CUSTOM_TOKEN": "cval",
                "UA_NAME": "ua-value",
                "SESSION_ID": "session=abc123",
            },
        )
        self.assertEqual(
            resolved_headers,
            {"Authorization": "tok", "X-Custom-Header": "cval", "User-Agent": "ua-value"},
        )
        self.assertEqual(resolved_cookies, "session=abc123")

    def test_missing_env_value_raises_generic_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            ffmpegfyMe.resolve_request_auth(
                {
                    "url": "https://cdn.example.com/video1.m3u8",
                    "output": "video1.mp4",
                    "headers": {"Authorization": "${API_TOKEN}"},
                },
                environment={},
            )
        message = str(ctx.exception)
        self.assertNotIn("API_TOKEN", message)
        self.assertNotIn("tok", message)

    def test_empty_env_value_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            ffmpegfyMe.resolve_request_auth(
                {
                    "url": "https://cdn.example.com/video1.m3u8",
                    "output": "video1.mp4",
                    "headers": {"Authorization": "${API_TOKEN}"},
                },
                environment={"API_TOKEN": ""},
            )

    def test_malformed_env_reference_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            ffmpegfyMe.resolve_request_auth(
                {
                    "url": "https://cdn.example.com/video1.m3u8",
                    "output": "video1.mp4",
                    "headers": {"Authorization": "Bearer ${API_TOKEN}"},
                },
                environment={"API_TOKEN": "tok"},
            )

    def test_header_value_with_control_characters_raises_value_error(self) -> None:
        for secret in ("tok\x00en", "tok\nen", "tok\x7f"):
            with self.subTest(secret=secret):
                with self.assertRaises(ValueError):
                    ffmpegfyMe.resolve_request_auth(
                        {
                            "url": "https://cdn.example.com/video1.m3u8",
                            "output": "video1.mp4",
                            "headers": {"Authorization": "${API_TOKEN}"},
                        },
                        environment={"API_TOKEN": secret},
                    )

    def test_malformed_cookie_env_reference_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            ffmpegfyMe.resolve_request_auth(
                {
                    "url": "https://cdn.example.com/video1.m3u8",
                    "output": "video1.mp4",
                    "cookies": "Bearer ${SESSION_ID}",
                },
                environment={"SESSION_ID": "session=abc123"},
            )

    def test_missing_cookie_env_value_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            ffmpegfyMe.resolve_request_auth(
                {
                    "url": "https://cdn.example.com/video1.m3u8",
                    "output": "video1.mp4",
                    "cookies": "${SESSION_ID}",
                },
                environment={},
            )

    def test_cookie_value_allows_lf_but_rejects_cr_and_nul(self) -> None:
        resolved_headers, resolved_cookies = ffmpegfyMe.resolve_request_auth(
            {
                "url": "https://cdn.example.com/video1.m3u8",
                "output": "video1.mp4",
                "cookies": "${SESSION_ID}",
            },
            environment={"SESSION_ID": "session=abc\ndef=ghi"},
        )
        self.assertEqual(resolved_headers, {})
        self.assertEqual(resolved_cookies, "session=abc\ndef=ghi")

        with self.assertRaises(ValueError):
            ffmpegfyMe.resolve_request_auth(
                {
                    "url": "https://cdn.example.com/video1.m3u8",
                    "output": "video1.mp4",
                    "cookies": "${SESSION_ID}",
                },
                environment={"SESSION_ID": "session=abc\rdef"},
            )

        with self.assertRaises(ValueError):
            ffmpegfyMe.resolve_request_auth(
                {
                    "url": "https://cdn.example.com/video1.m3u8",
                    "output": "video1.mp4",
                    "cookies": "${SESSION_ID}",
                },
                environment={"SESSION_ID": "session=abc\x00def"},
            )


if __name__ == "__main__":
    unittest.main()
