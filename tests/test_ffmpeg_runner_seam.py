import unittest
from pathlib import Path
from typing import Callable, List, Optional
from unittest import mock

import ffmpegfyMe


class FakeFFmpegRunner:
    """Deterministic fake standing in for the real FFmpeg subprocess seam."""

    def __init__(
        self,
        exit_code: Optional[int] = 0,
        progress_lines: Optional[List[str]] = None,
        cancel: bool = False,
    ) -> None:
        self.exit_code = exit_code if exit_code is not None else 0
        self.progress_lines = list(progress_lines or [])
        self.cancel = cancel
        self.commands: List[List[str]] = []
        self.cancelled = False
        self.emitted_lines: List[str] = []

    def __call__(
        self,
        command: List[str],
        on_output: Optional[Callable[[str], None]] = None,
    ) -> int:
        self.commands.append(list(command))
        if self.cancel:
            self.cancelled = True
            raise KeyboardInterrupt()
        if on_output is not None:
            for line in self.progress_lines:
                on_output(line)
                self.emitted_lines.append(line)
        return self.exit_code


def _make_item(url: str = "https://cdn.example.com/video1.m3u8") -> dict:
    return {"url": url, "output": "video1.mp4"}


class TestFakeFFmpegRunner(unittest.TestCase):
    def test_returns_success_on_zero_exit_code(self) -> None:
        fake = FakeFFmpegRunner(exit_code=0)
        self.assertEqual(fake(["ffmpeg", "-version"], on_output=None), 0)

    def test_returns_failure_on_nonzero_exit_code(self) -> None:
        fake = FakeFFmpegRunner(exit_code=1)
        self.assertEqual(fake(["ffmpeg", "-version"], on_output=None), 1)

    def test_emits_progress_lines_through_callback(self) -> None:
        fake = FakeFFmpegRunner(
            exit_code=0,
            progress_lines=["frame=  5 fps=0.25 q=0.0 size=123kB time=00:00:01.0"],
        )
        lines: List[str] = []
        exit_code = fake(["ffmpeg", "-i", "https://cdn.example.com/video1.m3u8"], on_output=lines.append)
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            lines,
            ["frame=  5 fps=0.25 q=0.0 size=123kB time=00:00:01.0"],
        )

    def test_raises_keyboardinterrupt_when_cancelled(self) -> None:
        fake = FakeFFmpegRunner(cancel=True)
        with self.assertRaises(KeyboardInterrupt):
            fake(["ffmpeg", "-version"], on_output=None)

    def test_records_executed_commands(self):
        fake = FakeFFmpegRunner(exit_code=0)
        fake(["ffmpeg", "-y", "-i", "https://cdn.example.com/video1.m3u8"], on_output=None)
        self.assertEqual(
            fake.commands,
            [["ffmpeg", "-y", "-i", "https://cdn.example.com/video1.m3u8"]],
        )


class TestDownloadStreamIntegration(unittest.TestCase):
    """download_stream must wire the injected runner through to real adapter behavior."""

    def setUp(self) -> None:
        self.url = "https://cdn.example.com/video1.m3u8"
        self.output_path = Path("out") / "video1.mp4"

    def test_success_returns_true_for_zero_exit_code(self) -> None:
        fake = FakeFFmpegRunner(exit_code=0)
        self.assertTrue(ffmpegfyMe.download_stream(self.url, self.output_path, runner=fake))
        self.assertEqual(len(fake.commands), 1)

    def test_failure_returns_false_for_nonzero_exit_code(self) -> None:
        fake = FakeFFmpegRunner(exit_code=1)
        self.assertFalse(ffmpegfyMe.download_stream(self.url, self.output_path, runner=fake))
        self.assertEqual(len(fake.commands), 1)

    def test_runner_receives_ffmpeg_command_with_url_and_output(self) -> None:
        fake = FakeFFmpegRunner(exit_code=0)
        self.assertTrue(ffmpegfyMe.download_stream(self.url, self.output_path, runner=fake))
        cmd = fake.commands[0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertEqual(cmd[1], "-y")
        self.assertEqual(cmd[2], "-i")
        self.assertEqual(cmd[3], self.url)
        self.assertEqual(cmd[-1], str(self.output_path))

    def test_progress_lines_flow_through_callback(self) -> None:
        fake = FakeFFmpegRunner(
            exit_code=0,
            progress_lines=["frame=  5 fps=0.25 q=0.0 size=123kB time=00:00:01.0"],
        )
        self.assertTrue(ffmpegfyMe.download_stream(self.url, self.output_path, runner=fake))
        self.assertEqual(
            fake.emitted_lines,
            ["frame=  5 fps=0.25 q=0.0 size=123kB time=00:00:01.0"],
        )

    def test_cancelled_runner_propagates_keyboard_interrupt(self) -> None:
        fake = FakeFFmpegRunner(cancel=True)
        with self.assertRaises(KeyboardInterrupt):
            ffmpegfyMe.download_stream(self.url, self.output_path, runner=fake)


class TestRealFFmpegAdapter(unittest.TestCase):
    def test_returns_exit_code_from_subprocess(self) -> None:
        with mock.patch("ffmpegfyMe.subprocess.Popen") as popen:
            popen.return_value.poll.return_value = 0
            popen.return_value.returncode = 0
            exit_code = ffmpegfyMe.run_ffmpeg(["ffmpeg", "-version"])
        self.assertEqual(exit_code, 0)
        popen.assert_called_once()

    def test_forwards_matching_output_lines_to_callback(self) -> None:
        with mock.patch("ffmpegfyMe.subprocess.Popen") as popen:
            process = popen.return_value
            process.poll.side_effect = [None, 0]
            process.stdout.readline.return_value = "frame=  5 fps=0.25 q=0.0 size=123kB time=00:00:01.0"
            process.returncode = 0
            lines: List[str] = []
            exit_code = ffmpegfyMe.run_ffmpeg(
                ["ffmpeg", "-i", "https://cdn.example.com/video1.m3u8"],
                on_output=lines.append,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            lines,
            ["frame=  5 fps=0.25 q=0.0 size=123kB time=00:00:01.0"],
        )


if __name__ == "__main__":
    unittest.main()
