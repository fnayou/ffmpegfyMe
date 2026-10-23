import io
import unittest
from contextlib import redirect_stdout
from typing import Dict, List
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
