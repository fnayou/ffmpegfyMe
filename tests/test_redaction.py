import io
import subprocess
import unittest
from contextlib import redirect_stdout
from typing import Dict, List, Tuple
from unittest import mock

import ffmpegfyMe


SIGNED_URL_SENTINEL = "https://cdn.example.com/private/video.m3u8?token=abc&sig=supersecretvalue"


class InteractiveMenuRedactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.links: List[Dict[str, str]] = [
            {"url": SIGNED_URL_SENTINEL, "output": "video1.mp4"},
            {"url": SIGNED_URL_SENTINEL, "output": "video2.mp4"},
        ]

    def test_interactive_menu_exits_cleanly_without_source_url(self) -> None:
        buffer = io.StringIO()
        with mock.patch("builtins.input", return_value="q"), redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as ctx:
                ffmpegfyMe.interactive_menu(self.links)
        self.assertEqual(ctx.exception.code, 0)
        output = buffer.getvalue()
        self.assertNotIn(SIGNED_URL_SENTINEL, output)
        self.assertNotIn("token=abc", output)
        self.assertNotIn("sig=supersecretvalue", output)
        self.assertIn("video1.mp4", output)
        self.assertIn("video2.mp4", output)


class RunFFmpegErrorRedactionTests(unittest.TestCase):
    AUTH_SENTINEL = "Bearer supersecret-token-value"
    COOKIE_SENTINEL = "session=supersecret-session-value"

    def _run_ffmpeg_with_error(self, exc: BaseException) -> Tuple[int, str]:
        command = [
            "ffmpeg", "-y",
            "-protocol_whitelist", "http,https,tcp,tls,crypto",
            "-i", SIGNED_URL_SENTINEL,
            "-headers", f"Authorization: {self.AUTH_SENTINEL}",
            "-cookies", self.COOKIE_SENTINEL,
            "-c", "copy", "out/video1.mp4",
        ]
        buffer = io.StringIO()
        with mock.patch("ffmpegfyMe.subprocess.Popen", side_effect=exc):
            with redirect_stdout(buffer):
                exit_code = ffmpegfyMe.run_ffmpeg(command)
        return exit_code, buffer.getvalue()

    def test_run_ffmpeg_error_output_excludes_secrets_and_keeps_safe_message(self) -> None:
        error = subprocess.SubprocessError(
            f"ffmpeg failed: {SIGNED_URL_SENTINEL} auth={self.AUTH_SENTINEL} cookie={self.COOKIE_SENTINEL}"
        )
        exit_code, output = self._run_ffmpeg_with_error(error)
        self.assertEqual(exit_code, 1)
        self.assertNotIn(SIGNED_URL_SENTINEL, output)
        self.assertNotIn("token=abc", output)
        self.assertNotIn("sig=supersecretvalue", output)
        self.assertNotIn(self.AUTH_SENTINEL, output)
        self.assertNotIn(self.COOKIE_SENTINEL, output)
        self.assertIn("FFmpeg error", output)
        self.assertNotIn(str(error), output)

        runtime_error = RuntimeError(
            f"ffmpeg crashed: {SIGNED_URL_SENTINEL} auth={self.AUTH_SENTINEL} cookie={self.COOKIE_SENTINEL}"
        )
        exit_code, output = self._run_ffmpeg_with_error(runtime_error)
        self.assertEqual(exit_code, 1)
        self.assertNotIn(SIGNED_URL_SENTINEL, output)
        self.assertNotIn("token=abc", output)
        self.assertNotIn("sig=supersecretvalue", output)
        self.assertNotIn(self.AUTH_SENTINEL, output)
        self.assertNotIn(self.COOKIE_SENTINEL, output)
        self.assertIn("Unexpected error", output)
        self.assertNotIn(str(runtime_error), output)


class DownloadSummaryRedactionTests(unittest.TestCase):
    def test_download_summary_excludes_source_urls(self) -> None:
        downloads: List[Dict[str, str]] = [
            {"url": SIGNED_URL_SENTINEL, "output": "video1.mp4"},
            {"url": SIGNED_URL_SENTINEL, "output": "video2.mp4"},
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            ffmpegfyMe.display_download_summary(downloads, 0)
        output = buffer.getvalue()
        self.assertNotIn(SIGNED_URL_SENTINEL, output)
        self.assertNotIn("token=abc", output)
        self.assertNotIn("sig=supersecretvalue", output)
        self.assertIn("video1.mp4", output)
        self.assertIn("video2.mp4", output)


if __name__ == "__main__":
    unittest.main()
