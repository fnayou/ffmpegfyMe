import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import ffmpegfyMe


STABLE_ITEM_KEY = "stable:video-1:video1.mp4"
SHA256_KEY_PREFIX = "sha256:"


def _sha256_key(url: str, output: str) -> str:
    digest_source = json.dumps([url, output], separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return f"{SHA256_KEY_PREFIX}{digest}"


def _entry(status: str, output: str) -> Dict[str, str]:
    return {"status": status, "output": output}


class ItemStateKeyTests(unittest.TestCase):
    def test_key_uses_stable_id_plus_output_when_id_supplied(self) -> None:
        item = {
            "url": "https://cdn.example.com/video1.m3u8",
            "output": "video1.mp4",
            "id": "video-1",
        }
        self.assertEqual(ffmpegfyMe.item_state_key(item), "stable:video-1:video1.mp4")

    def test_key_uses_sha256_of_url_and_output_when_id_missing(self) -> None:
        item = {"url": "https://cdn.example.com/video1.m3u8", "output": "video1.mp4"}
        self.assertEqual(
            ffmpegfyMe.item_state_key(item),
            _sha256_key("https://cdn.example.com/video1.m3u8", "video1.mp4"),
        )

    def test_key_is_stable_for_same_url_and_output(self) -> None:
        item = {"url": "https://cdn.example.com/video1.m3u8", "output": "video1.mp4"}
        self.assertEqual(
            ffmpegfyMe.item_state_key(item),
            ffmpegfyMe.item_state_key({"url": item["url"], "output": item["output"]}),
        )

    def test_key_changes_when_url_or_output_changes(self) -> None:
        base = {"url": "https://cdn.example.com/video1.m3u8", "output": "video1.mp4"}
        self.assertNotEqual(
            ffmpegfyMe.item_state_key(base),
            ffmpegfyMe.item_state_key({**base, "url": "https://cdn.example.com/video2.m3u8"}),
        )
        self.assertNotEqual(
            ffmpegfyMe.item_state_key(base),
            ffmpegfyMe.item_state_key({**base, "output": "video2.mp4"}),
        )

    def test_key_changes_with_stable_id(self) -> None:
        item_a = {"url": "https://cdn.example.com/video1.m3u8", "output": "video1.mp4", "id": "video-1"}
        item_b = {"url": "https://cdn.example.com/video1.m3u8", "output": "video1.mp4", "id": "video-2"}
        self.assertNotEqual(ffmpegfyMe.item_state_key(item_a), ffmpegfyMe.item_state_key(item_b))


class ItemStateStatusTests(unittest.TestCase):
    def test_state_statuses_are_pending_succeeded_or_failed(self) -> None:
        self.assertEqual(set(ffmpegfyMe.ITEM_STATUSES), {"pending", "succeeded", "failed"})


class LoadItemStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.state_file = Path(self._tmp_dir.name) / "batch_state.json"

    def test_load_missing_state_file_returns_empty_items(self) -> None:
        self.assertEqual(ffmpegfyMe.load_item_state(self.state_file), {})

    def test_save_and_load_round_trip_items(self) -> None:
        items = {
            "stable:video-1:video1.mp4": _entry("succeeded", "video1.mp4"),
            "sha256:abc123": _entry("failed", "video2.mp4"),
        }
        ffmpegfyMe.save_item_state(self.state_file, items)
        self.assertEqual(ffmpegfyMe.load_item_state(self.state_file), items)

    def test_save_writes_versioned_state_with_items_mapping(self) -> None:
        items = {"stable:video-1:video1.mp4": _entry("pending", "video1.mp4")}
        ffmpegfyMe.save_item_state(self.state_file, items)
        raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(raw["version"], 1)
        self.assertEqual(raw["items"], items)

    def test_save_replace_failure_leaves_previous_state_intact(self) -> None:
        ffmpegfyMe.save_item_state(
            self.state_file,
            {"stable:video-1:video1.mp4": _entry("succeeded", "video1.mp4")},
        )
        before = self.state_file.read_text(encoding="utf-8")
        with mock.patch("ffmpegfyMe.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                ffmpegfyMe.save_item_state(
                    self.state_file,
                    {"sha256:newkey": _entry("failed", "video2.mp4")},
                )
        self.assertEqual(self.state_file.read_text(encoding="utf-8"), before)

    def test_saved_state_contains_only_status_and_output_and_no_urls(self) -> None:
        item = {
            "url": "https://cdn.example.com/private/video1.m3u8?token=supersecretvalue",
            "output": "video1.mp4",
            "headers": {"Authorization": "${API_TOKEN}"},
            "cookies": "${SESSION_ID}",
        }
        key = ffmpegfyMe.item_state_key(item)
        items = {key: _entry("pending", item["output"])}
        ffmpegfyMe.save_item_state(self.state_file, items)

        raw = self.state_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        self.assertEqual(set(data), {"version", "items"})
        self.assertEqual(len(data["items"]), 1)
        entry = next(iter(data["items"].values()))
        self.assertEqual(set(entry), {"status", "output"})
        self.assertNotIn("https://", raw)
        self.assertNotIn("${", raw)
        self.assertNotIn("supersecretvalue", raw)
        self.assertEqual(key, ffmpegfyMe.item_state_key(item))


if __name__ == "__main__":
    unittest.main()
