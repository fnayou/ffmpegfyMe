import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ffmpegfyMe


class FakeDownloadRunner:
    def __init__(self, exit_code: int = 0, interrupt: bool = False) -> None:
        self.exit_code = exit_code
        self.interrupt = interrupt
        self.commands = []

    def __call__(self, command, on_output=None) -> int:
        self.commands.append(list(command))
        output_path = Path(command[-1])
        output_path.write_bytes(b"partial" if self.interrupt or self.exit_code != 0 else b"new-content")
        if self.interrupt:
            raise KeyboardInterrupt()
        return self.exit_code


class TemporaryOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)

    def test_runner_command_uses_distinct_temp_path_with_same_directory_and_suffix(self) -> None:
        for suffix in (".mp4", ".mkv"):
            with self.subTest(suffix=suffix):
                output_path = self.output_dir / f"video{suffix}"
                runner = FakeDownloadRunner()
                self.assertTrue(
                    ffmpegfyMe.download_stream(
                        "https://cdn.example.com/video.m3u8",
                        output_path,
                        runner=runner,
                    )
                )
                command_output = Path(runner.commands[0][-1])
                self.assertNotEqual(command_output, output_path)
                self.assertEqual(command_output.parent, output_path.parent)
                self.assertEqual(command_output.suffix, suffix)

    def test_success_promotes_fake_bytes_and_removes_temp_file(self) -> None:
        output_path = self.output_dir / "video.mp4"
        runner = FakeDownloadRunner()
        self.assertTrue(
            ffmpegfyMe.download_stream(
                "https://cdn.example.com/video.m3u8",
                output_path,
                runner=runner,
            )
        )
        self.assertEqual(output_path.read_bytes(), b"new-content")
        self.assertNotEqual(Path(runner.commands[0][-1]), output_path)
        self.assertEqual(list(self.output_dir.iterdir()), [output_path])

    def test_nonzero_exit_removes_partial_temp_and_leaves_final_absent(self) -> None:
        output_path = self.output_dir / "video.mp4"
        runner = FakeDownloadRunner(exit_code=1)
        self.assertFalse(
            ffmpegfyMe.download_stream(
                "https://cdn.example.com/video.m3u8",
                output_path,
                runner=runner,
            )
        )
        self.assertFalse(output_path.exists())
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_keyboard_interrupt_cleans_partial_temp_and_propagates(self) -> None:
        output_path = self.output_dir / "video.mp4"
        runner = FakeDownloadRunner(interrupt=True)
        with self.assertRaises(KeyboardInterrupt):
            ffmpegfyMe.download_stream(
                "https://cdn.example.com/video.m3u8",
                output_path,
                runner=runner,
            )
        self.assertFalse(output_path.exists())
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_existing_output_conflicts_without_running_or_changing_file(self) -> None:
        output_path = self.output_dir / "video.mp4"
        output_path.write_bytes(b"existing")
        runner = FakeDownloadRunner()
        self.assertFalse(
            ffmpegfyMe.download_stream(
                "https://cdn.example.com/video.m3u8",
                output_path,
                runner=runner,
            )
        )
        self.assertEqual(runner.commands, [])
        self.assertEqual(output_path.read_bytes(), b"existing")

    def test_explicit_overwrite_replaces_only_after_runner_success(self) -> None:
        output_path = self.output_dir / "video.mp4"
        output_path.write_bytes(b"existing")
        failing_runner = FakeDownloadRunner(exit_code=1)
        self.assertFalse(
            ffmpegfyMe.download_stream(
                "https://cdn.example.com/video.m3u8",
                output_path,
                runner=failing_runner,
                allow_overwrite=True,
            )
        )
        self.assertEqual(output_path.read_bytes(), b"existing")

        successful_runner = FakeDownloadRunner()
        self.assertTrue(
            ffmpegfyMe.download_stream(
                "https://cdn.example.com/video.m3u8",
                output_path,
                runner=successful_runner,
                allow_overwrite=True,
            )
        )
        self.assertEqual(output_path.read_bytes(), b"new-content")
        self.assertNotEqual(Path(successful_runner.commands[0][-1]), output_path)
        self.assertEqual(list(self.output_dir.iterdir()), [output_path])

    def test_download_stream_forwards_inactivity_timeout_to_run_ffmpeg(self) -> None:
        output_path = self.output_dir / "video.mp4"
        with mock.patch.object(ffmpegfyMe, "run_ffmpeg") as mocked_run_ffmpeg:
            mocked_run_ffmpeg.return_value = 0
            self.assertTrue(
                ffmpegfyMe.download_stream(
                    "https://cdn.example.com/video.m3u8",
                    output_path,
                    inactivity_timeout=42.0,
                )
            )
        self.assertEqual(mocked_run_ffmpeg.call_args.kwargs.get("inactivity_timeout"), 42.0)

    def test_ffmpeg_inactivity_timeout_leaves_no_final_output_or_temp_file(self) -> None:
        output_path = self.output_dir / "video.mp4"
        with mock.patch.object(ffmpegfyMe, "run_ffmpeg") as mocked_run_ffmpeg:
            mocked_run_ffmpeg.side_effect = ffmpegfyMe.FFmpegInactivityTimeout("FFmpeg inactivity timeout exceeded.")
            self.assertFalse(
                ffmpegfyMe.download_stream(
                    "https://cdn.example.com/video.m3u8",
                    output_path,
                    inactivity_timeout=42.0,
                )
            )
        self.assertFalse(output_path.exists())
        self.assertEqual(list(self.output_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
