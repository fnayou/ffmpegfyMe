import io
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
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


class RunFFmpegProgressRedactionTests(unittest.TestCase):
    URL_SENTINEL = "https://cdn.example/private.m3u8?token=supersecret-progress-token"
    HEADER_SENTINEL = "Authorization: Bearer supersecret-progress-header"
    COOKIE_SENTINEL = "session=supersecret-progress-cookie"
    SEGMENT_SENTINEL = "https://cdn.example.com/private/segment-1.m3u8?token=supersecret-segment-token"

    def test_run_ffmpeg_progress_lines_redact_secrets(self) -> None:
        command = [
            "ffmpeg", "-y",
            "-protocol_whitelist", "http,https,tcp,tls,crypto",
            "-i", self.URL_SENTINEL,
            "-headers", self.HEADER_SENTINEL,
            "-cookies", self.COOKIE_SENTINEL,
            "-c", "copy", "out/video1.mp4",
        ]
        frame_line = (
            f"frame=  5 fps=0.25 q=0.0 size=123kB time=00:00:01.0 "
            f"sources={self.URL_SENTINEL} "
            f"headers={self.HEADER_SENTINEL} "
            f"cookies={self.COOKIE_SENTINEL} "
            f"segment={self.SEGMENT_SENTINEL}"
        )
        buffer = io.StringIO()
        lines: List[str] = []
        with mock.patch("ffmpegfyMe.subprocess.Popen") as popen:
            process = popen.return_value
            process.poll.side_effect = [None, 0]
            process.stdout.readline.return_value = frame_line + "\n"
            process.returncode = 0
            with redirect_stdout(buffer):
                exit_code = ffmpegfyMe.run_ffmpeg(command, on_output=lines.append)
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("frame=", lines[0])
        self.assertNotIn(self.URL_SENTINEL, lines[0])
        self.assertNotIn(self.HEADER_SENTINEL, lines[0])
        self.assertNotIn(self.COOKIE_SENTINEL, lines[0])
        self.assertNotIn(self.SEGMENT_SENTINEL, lines[0])
        self.assertNotIn("https://", lines[0])
        stdout_output = buffer.getvalue()
        self.assertIn("frame=", stdout_output)
        self.assertNotIn(self.URL_SENTINEL, stdout_output)
        self.assertNotIn(self.HEADER_SENTINEL, stdout_output)
        self.assertNotIn(self.COOKIE_SENTINEL, stdout_output)
        self.assertNotIn(self.SEGMENT_SENTINEL, stdout_output)
        self.assertNotIn("https://", stdout_output)


class DownloadStreamProgressRedactionTests(unittest.TestCase):
    URL_SENTINEL = "https://cdn.example.com/private/video.m3u8?token=abc&sig=supersecretvalue"

    def test_download_stream_runner_progress_output_redacts_secrets(self) -> None:
        buffer = io.StringIO()

        def fake_runner(cmd, on_output=None):
            on_output(f"frame=2 sources={self.URL_SENTINEL}")
            return 0

        with redirect_stdout(buffer):
            result = ffmpegfyMe.download_stream(
                self.URL_SENTINEL,
                Path("out") / "video1.mp4",
                runner=fake_runner,
            )

        self.assertTrue(result)
        stdout_output = buffer.getvalue()
        self.assertIn("frame=2", stdout_output)
        self.assertNotIn(self.URL_SENTINEL, stdout_output)
        self.assertNotIn("https://", stdout_output)


class DownloadStreamRunnerErrorRedactionTests(unittest.TestCase):
    SIGNED_URL = "https://cdn.example.com/private/video.m3u8?token=abc&sig=supersecretvalue"
    AUTH_HEADER_VALUE = "Authorization: Bearer header-secret-123"
    COOKIE_VALUE = "session=cookie-secret-456"

    def test_download_stream_runner_error_redacts_secrets_and_returns_false(self) -> None:
        buffer = io.StringIO()

        def failing_runner(cmd, on_output=None):
            raise RuntimeError(
                f"ffmpeg crashed: {self.SIGNED_URL} auth={self.AUTH_HEADER_VALUE} cookie={self.COOKIE_VALUE}"
            )

        with redirect_stdout(buffer):
            result = ffmpegfyMe.download_stream(
                self.SIGNED_URL,
                Path("out") / "video1.mp4",
                runner=failing_runner,
                headers={"Authorization": "Bearer header-secret-123"},
                cookies="session=cookie-secret-456",
            )

        self.assertFalse(result)
        output = buffer.getvalue()
        self.assertNotIn(self.SIGNED_URL, output)
        self.assertNotIn("token=abc", output)
        self.assertNotIn("sig=supersecretvalue", output)
        self.assertNotIn("header-secret-123", output)
        self.assertNotIn("cookie-secret-456", output)


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
