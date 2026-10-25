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

    def test_legacy_last_index_does_not_infer_success_and_preserves_output(self) -> None:
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
        self._write_manifest([item_a, item_b])
        self.batch_dir.mkdir()
        (self.batch_dir / "video-a.mp4").write_bytes(b"keep")
        self.state_file.write_text(json.dumps({"last_index": 1}), encoding="utf-8")
        runner = FakeMainRunner()
        output = io.StringIO()
        with mock.patch("builtins.input", side_effect=["y", "y", "2"]):
            with redirect_stdout(output):
                ffmpegfyMe.main(runner=runner)

        report = output.getvalue()
        self.assertIn("legacy", report.lower())
        self.assertIn("last_index", report)
        self.assertIn("cannot prove", report)

        self.assertEqual((self.batch_dir / "video-a.mp4").read_bytes(), b"keep")
        self.assertEqual(len(runner.commands), 1)
        self.assertEqual(runner.commands[0][runner.commands[0].index("-i") + 1], item_b["url"])
        self.assertEqual((self.batch_dir / "video-b.mp4").read_bytes(), b"new-content")
        saved = ffmpegfyMe.load_item_state(self.state_file)
        key_a = ffmpegfyMe.item_state_key(item_a)
        key_b = ffmpegfyMe.item_state_key(item_b)
        self.assertEqual(saved[key_a]["status"], "failed")
        self.assertEqual(saved[key_b]["status"], "succeeded")

    def test_declining_legacy_reset_preserves_progress_and_output(self) -> None:
        self._write_manifest([{"url": "https://cdn.example.com/a.m3u8", "output": "video-a.mp4"}])
        self.batch_dir.mkdir()
        output_path = self.batch_dir / "video-a.mp4"
        output_path.write_bytes(b"keep")
        legacy_bytes = b'{"last_index": 1}'
        self.state_file.write_bytes(legacy_bytes)
        runner = FakeMainRunner()

        with mock.patch("builtins.input", side_effect=["n"]):
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    ffmpegfyMe.main(runner=runner)

        self.assertEqual(self.state_file.read_bytes(), legacy_bytes)
        self.assertEqual(output_path.read_bytes(), b"keep")
        self.assertEqual(runner.commands, [])

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

    def test_empty_manifest_exits_without_processing(self) -> None:
        self._write_manifest([])
        runner = FakeMainRunner()
        output = io.StringIO()

        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as ctx:
                ffmpegfyMe.main(runner=runner)

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("No downloads found", output.getvalue())
        self.assertEqual(runner.commands, [])
        self.assertFalse(self.state_file.exists())

    def test_resetting_saved_progress_restarts_item(self) -> None:
        item = {"id": "item-a", "url": "https://cdn.example.com/a.m3u8", "output": "video-a.mp4"}
        self._write_manifest([item])
        ffmpegfyMe.save_item_state(
            self.state_file,
            {ffmpegfyMe.item_state_key(item): {"status": "succeeded", "output": "video-a.mp4"}},
        )
        runner = FakeMainRunner()

        self._run_main(["y", "y", "2"], runner)

        self.assertEqual(len(runner.commands), 1)
        self.assertEqual((self.batch_dir / "video-a.mp4").read_bytes(), b"new-content")
        self.assertEqual(
            ffmpegfyMe.load_item_state(self.state_file),
            {ffmpegfyMe.item_state_key(item): {"status": "succeeded", "output": "video-a.mp4"}},
        )

    def test_manual_failed_item_can_continue_to_next_item(self) -> None:
        item_a = {"url": "https://cdn.example.com/a.m3u8", "output": "video-a.mp4"}
        item_b = {"url": "https://cdn.example.com/b.m3u8", "output": "video-b.mp4"}
        self._write_manifest([item_a, item_b])

        class FailFirstItemRunner:
            def __init__(self) -> None:
                self.commands = []

            def __call__(self, command, on_output=None) -> int:
                self.commands.append(list(command))
                if command[command.index("-i") + 1] == item_a["url"]:
                    return 1
                Path(command[-1]).write_bytes(b"new-content")
                return 0

        runner = FailFirstItemRunner()
        with mock.patch("builtins.input", side_effect=["y", "1", "", "y", ""]):
            with mock.patch("ffmpegfyMe.time.sleep"):
                with redirect_stdout(io.StringIO()):
                    ffmpegfyMe.main(runner=runner)

        attempted_urls = [command[command.index("-i") + 1] for command in runner.commands]
        self.assertEqual(attempted_urls.count(item_a["url"]), 3)
        self.assertIn(item_b["url"], attempted_urls)
        self.assertEqual((self.batch_dir / "video-b.mp4").read_bytes(), b"new-content")

    def test_manual_failed_item_can_stop_batch(self) -> None:
        item_a = {"url": "https://cdn.example.com/a.m3u8", "output": "video-a.mp4"}
        item_b = {"url": "https://cdn.example.com/b.m3u8", "output": "video-b.mp4"}
        self._write_manifest([item_a, item_b])

        class FailRunner:
            def __init__(self) -> None:
                self.commands = []

            def __call__(self, command, on_output=None) -> int:
                self.commands.append(list(command))
                return 1

        runner = FailRunner()
        with mock.patch("builtins.input", side_effect=["y", "1", "", "n"]):
            with mock.patch("ffmpegfyMe.time.sleep"):
                with redirect_stdout(io.StringIO()):
                    ffmpegfyMe.main(runner=runner)

        attempted_urls = [command[command.index("-i") + 1] for command in runner.commands]
        self.assertEqual(attempted_urls, [item_a["url"]] * 3)
        self.assertFalse((self.batch_dir / "video-b.mp4").exists())

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
        self.assertIn("Failed downloads:", report)
        self.assertIn("video-a.mp4", report)
        self.assertLess(report.index("Failed downloads:"), report.index("All done"))


if __name__ == "__main__":
    unittest.main()
