import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import List
from unittest import mock

import ffmpegfyMe


class FakeMainRunner:
    def __init__(self) -> None:
        self.commands: List[List[str]] = []

    def __call__(self, command, on_output=None) -> int:
        self.commands.append(list(command))
        Path(command[-1]).write_bytes(b"new-content")
        return 0


class MainProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.in_dir = root / "in"
        self.out_dir = root / "out"
        self.progress_dir = root / "progress"
        self.in_dir.mkdir()
        self.out_dir.mkdir()
        self.progress_dir.mkdir()
        self.batch_dir = self.out_dir / "batch"
        self.manifest = self.in_dir / "batch.json"
        self.state_file = self.progress_dir / "batch_state.json"

        patches = [
            mock.patch.object(ffmpegfyMe, "IN_DIR", self.in_dir),
            mock.patch.object(ffmpegfyMe, "OUT_DIR", self.out_dir),
            mock.patch.object(ffmpegfyMe, "PROGRESS_DIR", self.progress_dir),
            mock.patch.object(ffmpegfyMe, "check_ffmpeg", return_value=True),
            mock.patch.object(ffmpegfyMe, "choose_json_file", return_value=self.manifest),
            mock.patch.object(ffmpegfyMe, "prompt_download_dir", return_value=self.batch_dir),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _write_manifest(self, items) -> None:
        self.manifest.write_text(json.dumps(items), encoding="utf-8")

    def _run_main(self, answers, runner):
        with mock.patch("builtins.input", side_effect=answers) as input_mock:
            with redirect_stdout(io.StringIO()):
                ffmpegfyMe.main(runner=runner)
        return input_mock

    def test_resume_after_manifest_reorder_skips_only_matching_success(self) -> None:
        item_a = {
            "id": "item-a",
            "url": "https://cdn.example.com/a.m3u8",
            "output": "video-a.mp4",
        }
        item_b = {
            "id": "item-b",
            "url": "https://cdn.example.com/b.m3u8",
            "output": "video-b.mp4",
        }
        self._write_manifest([item_b, item_a])
        self.batch_dir.mkdir()
        (self.batch_dir / "video-a.mp4").write_bytes(b"already-complete")
        key_a = ffmpegfyMe.item_state_key(item_a)
        ffmpegfyMe.save_item_state(
            self.state_file,
            {key_a: {"status": "succeeded", "output": "video-a.mp4"}},
        )
        runner = FakeMainRunner()

        self._run_main(["n", "y", "2"], runner)

        self.assertEqual(len(runner.commands), 1)
        self.assertEqual(runner.commands[0][runner.commands[0].index("-i") + 1], item_b["url"])
        self.assertEqual((self.batch_dir / "video-a.mp4").read_bytes(), b"already-complete")
        self.assertEqual((self.batch_dir / "video-b.mp4").read_bytes(), b"new-content")
        saved = ffmpegfyMe.load_item_state(self.state_file)
        self.assertEqual(saved[key_a], {"status": "succeeded", "output": "video-a.mp4"})
        key_b = ffmpegfyMe.item_state_key(item_b)
        self.assertEqual(saved[key_b], {"status": "succeeded", "output": "video-b.mp4"})

    def test_automatic_conflict_preserves_output_without_prompting_overwrite(self) -> None:
        item = {
            "id": "item-a",
            "url": "https://cdn.example.com/a.m3u8",
            "output": "video-a.mp4",
        }
        self._write_manifest([item])
        self.batch_dir.mkdir()
        output_path = self.batch_dir / "video-a.mp4"
        output_path.write_bytes(b"existing")
        runner = FakeMainRunner()

        input_mock = self._run_main(["y", "2"], runner)

        self.assertEqual(input_mock.call_count, 2)
        self.assertEqual(runner.commands, [])
        self.assertEqual(output_path.read_bytes(), b"existing")
        saved = ffmpegfyMe.load_item_state(self.state_file)
        self.assertEqual(
            saved[ffmpegfyMe.item_state_key(item)],
            {"status": "failed", "output": "video-a.mp4"},
        )

    def test_manual_mode_overwrites_only_after_explicit_yes(self) -> None:
        item = {
            "id": "item-a",
            "url": "https://cdn.example.com/a.m3u8",
            "output": "video-a.mp4",
        }
        self._write_manifest([item])
        self.batch_dir.mkdir()
        output_path = self.batch_dir / "video-a.mp4"
        output_path.write_bytes(b"existing")
        runner = FakeMainRunner()

        self._run_main(["y", "1", "", "y"], runner)

        self.assertEqual(len(runner.commands), 1)
        self.assertEqual(output_path.read_bytes(), b"new-content")
        saved = ffmpegfyMe.load_item_state(self.state_file)
        self.assertEqual(
            saved[ffmpegfyMe.item_state_key(item)],
            {"status": "succeeded", "output": "video-a.mp4"},
        )

    def test_invalid_inactivity_timeout_exits_before_ffmpeg_check_or_prompt(self) -> None:
        runner = FakeMainRunner()
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"FFMPEG_INACTIVITY_TIMEOUT": "not-a-number"}):
            with mock.patch.object(ffmpegfyMe, "check_ffmpeg", return_value=True) as check_ffmpeg_mock:
                with self.assertRaises(SystemExit) as ctx:
                    with redirect_stdout(output):
                        ffmpegfyMe.main(runner=runner)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("FFMPEG_INACTIVITY_TIMEOUT", output.getvalue())
        check_ffmpeg_mock.assert_not_called()

    def test_main_passes_resolved_inactivity_timeout_to_process_download_item(self) -> None:
        item = {
            "id": "item-a",
            "url": "https://cdn.example.com/a.m3u8",
            "output": "video-a.mp4",
        }
        self._write_manifest([item])
        self.batch_dir.mkdir()
        runner = FakeMainRunner()

        with mock.patch.dict(os.environ, {"FFMPEG_INACTIVITY_TIMEOUT": "42.5"}):
            with mock.patch.object(
                ffmpegfyMe,
                "process_download_item",
                return_value=True,
            ) as mocked_process:
                self._run_main(["y", "2"], runner)

        self.assertEqual(mocked_process.call_count, 1)
        self.assertEqual(mocked_process.call_args.kwargs.get("inactivity_timeout"), 42.5)

    def test_process_download_item_passes_inactivity_timeout_to_download_with_retry(self) -> None:
        item = {
            "id": "item-a",
            "url": "https://cdn.example.com/a.m3u8",
            "output": "video-a.mp4",
        }
        state_file = self.progress_dir / "batch_state.json"

        with mock.patch.object(ffmpegfyMe, "download_with_retry", return_value=True) as mocked_download_with_retry:
            success = ffmpegfyMe.process_download_item(
                item,
                self.batch_dir / "video-a.mp4",
                state_file,
                {},
                inactivity_timeout=42.5,
            )

        self.assertTrue(success)
        self.assertEqual(mocked_download_with_retry.call_count, 1)
        self.assertEqual(mocked_download_with_retry.call_args.kwargs.get("inactivity_timeout"), 42.5)

    def test_failure_is_reported_after_batch_and_later_items_continue(self) -> None:
        item_a = {"url": "https://cdn.example.com/a.m3u8", "output": "video-a.mp4"}
        item_b = {"url": "https://cdn.example.com/b.m3u8", "output": "video-b.mp4"}
        self._write_manifest([item_a, item_b])

        class FailFirstItemRunner:
            def __init__(self) -> None:
                self.commands = []

            def __call__(self, command, on_output=None) -> int:
                self.commands.append(list(command))
                url = command[command.index("-i") + 1]
                if url == item_a["url"]:
                    return 1
                Path(command[-1]).write_bytes(b"new-content")
                return 0

        runner = FailFirstItemRunner()
        output = io.StringIO()
        with mock.patch("builtins.input", side_effect=["y", "2"]):
            with mock.patch("ffmpegfyMe.time.sleep"):
                with redirect_stdout(output):
                    ffmpegfyMe.main(runner=runner)

        attempted_urls = [command[command.index("-i") + 1] for command in runner.commands]
        self.assertEqual(attempted_urls.count(item_a["url"]), 3)
        self.assertIn(item_b["url"], attempted_urls)
        report = output.getvalue()
        self.assertIn("❌ Failed downloads:", report)
        self.assertIn("video-a.mp4", report)
        self.assertLess(report.index("❌ Failed downloads:"), report.index("✅ All done"))


if __name__ == "__main__":
    unittest.main()
