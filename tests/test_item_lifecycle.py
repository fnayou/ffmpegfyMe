import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import ffmpegfyMe


class FakeItemRunner:
    """Fake ffmpeg runner: records commands, writes bytes to temp output, reads state file."""

    def __init__(
        self,
        exit_code: Optional[int] = 0,
        interrupt: bool = False,
        state_file: Optional[Path] = None,
        content: bytes = b"final-video-bytes",
    ) -> None:
        self.exit_code = exit_code if exit_code is not None else 0
        self.interrupt = interrupt
        self.state_file = state_file
        self.content = content
        self.commands: List[List[str]] = []
        self.seen_states: List[Dict[str, Any]] = []

    def __call__(self, command, on_output=None) -> int:
        self.commands.append(list(command))
        Path(command[-1]).write_bytes(self.content)
        if self.state_file is not None and self.state_file.exists():
            with open(self.state_file, "r") as f:
                self.seen_states.append(json.load(f))
        if self.interrupt:
            raise KeyboardInterrupt()
        return self.exit_code


class ProcessDownloadItemLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.output_dir = Path(self._tmp_dir.name) / "out"
        self.progress_dir = Path(self._tmp_dir.name) / "progress"
        self.output_dir.mkdir()
        self.progress_dir.mkdir()
        self.state_file = self.progress_dir / "batch_state.json"
        self.item_states: Dict[str, Dict[str, Any]] = {}
        self.item = {
            "url": "https://private.cdn.example.com/video1.m3u8?token=supersecretvalue",
            "output": "video1.mp4",
            "id": "video-1",
            "headers": {"Authorization": "${API_TOKEN}"},
            "cookies": "${SESSION_ID}",
        }
        self.output_path = self.output_dir / "video1.mp4"
        self.key = ffmpegfyMe.item_state_key(self.item)
        self._env_patch = mock.patch.dict(
            os.environ, {"API_TOKEN": "tok", "SESSION_ID": "session=abc"}
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    def _pending_state(self) -> Dict[str, Any]:
        return {
            "version": ffmpegfyMe.ITEM_STATE_VERSION,
            "items": {self.key: {"status": "pending", "output": "video1.mp4"}},
        }

    def test_matching_succeeded_state_with_existing_output_returns_true_without_runner(self) -> None:
        self.item_states[self.key] = {"status": "succeeded", "output": "video1.mp4"}
        self.output_path.write_bytes(b"already-there")
        runner = FakeItemRunner()

        result = ffmpegfyMe.process_download_item(
            self.item,
            self.output_path,
            self.state_file,
            self.item_states,
            runner=runner,
        )

        self.assertTrue(result)
        self.assertEqual(runner.commands, [])

    def test_existing_output_without_success_persists_failed_state_and_skips_runner(self) -> None:
        self.output_path.write_bytes(b"existing-bytes")
        runner = FakeItemRunner()

        result = ffmpegfyMe.process_download_item(
            self.item,
            self.output_path,
            self.state_file,
            self.item_states,
            runner=runner,
        )

        self.assertFalse(result)
        self.assertEqual(runner.commands, [])
        self.assertEqual(self.output_path.read_bytes(), b"existing-bytes")
        self.assertEqual(
            self.item_states[self.key],
            {"status": "failed", "output": "video1.mp4"},
        )
        on_disk = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            on_disk["items"][self.key],
            {"status": "failed", "output": "video1.mp4"},
        )

    def test_successful_run_writes_final_bytes_and_persists_succeeded_state(self) -> None:
        runner = FakeItemRunner(exit_code=0, state_file=self.state_file, content=b"final-video-bytes")

        result = ffmpegfyMe.process_download_item(
            self.item,
            self.output_path,
            self.state_file,
            self.item_states,
            runner=runner,
        )

        self.assertTrue(result)
        self.assertEqual(len(runner.commands), 1)
        self.assertEqual(self.output_path.read_bytes(), b"final-video-bytes")
        self.assertEqual(runner.seen_states, [self._pending_state()])
        self.assertEqual(
            self.item_states[self.key],
            {"status": "succeeded", "output": "video1.mp4"},
        )
        on_disk = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            on_disk,
            {
                "version": ffmpegfyMe.ITEM_STATE_VERSION,
                "items": {self.key: {"status": "succeeded", "output": "video1.mp4"}},
            },
        )
        raw = self.state_file.read_text(encoding="utf-8")
        self.assertNotIn("https://", raw)
        self.assertNotIn("${", raw)
        self.assertNotIn("supersecretvalue", raw)

    def test_failed_runner_returns_false_and_persists_failed_state(self) -> None:
        runner = FakeItemRunner(exit_code=1, state_file=self.state_file, content=b"partial-bytes")

        with mock.patch.dict(os.environ, {"API_TOKEN": "tok", "SESSION_ID": "session=abc"}):
            with mock.patch("ffmpegfyMe.time.sleep") as sleep:
                result = ffmpegfyMe.process_download_item(
                    self.item,
                    self.output_path,
                    self.state_file,
                    self.item_states,
                    runner=runner,
                )

        self.assertFalse(result)
        self.assertFalse(self.output_path.exists())
        self.assertEqual(list(self.output_dir.iterdir()), [])
        self.assertEqual(
            self.item_states[self.key],
            {"status": "failed", "output": "video1.mp4"},
        )
        self.assertTrue(sleep.called)

    def test_keyboard_interrupt_propagates_and_pending_state_persists(self) -> None:
        runner = FakeItemRunner(interrupt=True, state_file=self.state_file)

        with self.assertRaises(KeyboardInterrupt):
            ffmpegfyMe.process_download_item(
                self.item,
                self.output_path,
                self.state_file,
                self.item_states,
                runner=runner,
            )

        self.assertEqual(
            self.item_states[self.key],
            {"status": "pending", "output": "video1.mp4"},
        )
        on_disk = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["items"][self.key], {"status": "pending", "output": "video1.mp4"})
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_allow_overwrite_true_failure_preserves_then_success_replaces(self) -> None:
        self.output_path.write_bytes(b"existing-bytes")
        failing_runner = FakeItemRunner(exit_code=1, state_file=self.state_file, content=b"partial-bytes")

        with mock.patch.dict(os.environ, {"API_TOKEN": "tok", "SESSION_ID": "session=abc"}):
            with mock.patch("ffmpegfyMe.time.sleep"):
                self.assertFalse(
                    ffmpegfyMe.process_download_item(
                        self.item,
                        self.output_path,
                        self.state_file,
                        self.item_states,
                        runner=failing_runner,
                        allow_overwrite=True,
                    )
                )

        self.assertEqual(self.output_path.read_bytes(), b"existing-bytes")

        succeeding_runner = FakeItemRunner(exit_code=0, state_file=self.state_file, content=b"final-video-bytes")

        with mock.patch.dict(os.environ, {"API_TOKEN": "tok", "SESSION_ID": "session=abc"}):
            with mock.patch("ffmpegfyMe.time.sleep"):
                self.assertTrue(
                    ffmpegfyMe.process_download_item(
                        self.item,
                        self.output_path,
                        self.state_file,
                        self.item_states,
                        runner=succeeding_runner,
                        allow_overwrite=True,
                    )
                )

        self.assertEqual(self.output_path.read_bytes(), b"final-video-bytes")
        self.assertEqual(
            self.item_states[self.key],
            {"status": "succeeded", "output": "video1.mp4"},
        )


if __name__ == "__main__":
    unittest.main()
