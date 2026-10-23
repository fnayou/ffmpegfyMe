import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

import ffmpegfyMe

VALID_URL = "https://cdn.example.com/video1.m3u8?token=abc&sig=xyz"


class LoadDownloadsValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.manifest_dir = Path(self._tmp_dir.name)

    def write_manifest(self, data: Any) -> Path:
        path = self.manifest_dir / "batch.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def load(self, data: Any) -> List[Dict[str, str]]:
        return ffmpegfyMe.load_downloads(self.write_manifest(data))

    def assert_load_rejected(self, data: Any) -> None:
        with self.assertRaises(SystemExit):
            self.load(data)

    def test_accepts_top_level_list_of_objects(self) -> None:
        downloads = self.load([
            {"url": VALID_URL, "output": "video1.mp4"},
            {"url": "http://other.example.com/v2.m3u8", "output": "video2.mp4", "id": "video-2"},
        ])
        self.assertEqual(len(downloads), 2)
        self.assertEqual(downloads[0], {"url": VALID_URL, "output": "video1.mp4"})
        self.assertEqual(downloads[1]["id"], "video-2")

    def test_rejects_non_list_top_level(self) -> None:
        self.assert_load_rejected({"url": VALID_URL, "output": "video1.mp4"})

    def test_rejects_non_object_entries(self) -> None:
        self.assert_load_rejected(["https://cdn.example.com/video1.m3u8"])

    def test_rejects_missing_url_or_output(self) -> None:
        self.assert_load_rejected([{"output": "video1.mp4"}])
        self.assert_load_rejected([{"url": VALID_URL}])

    def test_rejects_empty_or_non_string_url_and_output(self) -> None:
        self.assert_load_rejected([{"url": "", "output": "video1.mp4"}])
        self.assert_load_rejected([{"url": VALID_URL, "output": ""}])
        self.assert_load_rejected([{"url": 123, "output": "video1.mp4"}])

    def test_rejects_unknown_fields(self) -> None:
        self.assert_load_rejected([
            {"url": VALID_URL, "output": "video1.mp4", "token": "secret"},
        ])

    def test_accepts_absolute_http_https_urls_with_signed_query(self) -> None:
        downloads = self.load([
            {"url": "http://cdn.example.com/video1.m3u8?token=abc&sig=xyz", "output": "video1.mp4"},
            {"url": VALID_URL, "output": "video2.mp4"},
        ])
        self.assertEqual(len(downloads), 2)

    def test_rejects_relative_or_non_http_urls(self) -> None:
        self.assert_load_rejected([{"url": "cdn.example.com/video1.m3u8", "output": "video1.mp4"}])
        self.assert_load_rejected([{"url": "ftp://cdn.example.com/video1.m3u8", "output": "video1.mp4"}])
        self.assert_load_rejected([{"url": "/local/path.m3u8", "output": "video1.mp4"}])

    def test_rejects_urls_with_userinfo_or_whitespace_or_bad_host(self) -> None:
        self.assert_load_rejected([{"url": "https://user:pass@cdn.example.com/video1.m3u8", "output": "video1.mp4"}])
        self.assert_load_rejected([{"url": "https://cdn.example.com/video 1.m3u8", "output": "video1.mp4"}])
        self.assert_load_rejected([{"url": "https://", "output": "video1.mp4"}])

    def test_rejects_unsafe_output_filenames(self) -> None:
        for output in [
            "",
            ".",
            "..",
            "subdir/video1.mp4",
            "subdir\\video1.mp4",
            "/absolute/path/video1.mp4",
            "video1.mp4",
        ]:
            if output == "video1.mp4":
                continue
            self.assert_load_rejected([{"url": VALID_URL, "output": output}])

    def test_rejects_output_with_control_characters(self) -> None:
        self.assert_load_rejected([{"url": VALID_URL, "output": "video1\x00.mp4"}])

    def test_accepts_safe_output_filenames(self) -> None:
        downloads = self.load([{"url": VALID_URL, "output": "my video1.mp4"}])
        self.assertEqual(downloads[0]["output"], "my video1.mp4")

    def test_rejects_duplicate_stable_ids(self) -> None:
        self.assert_load_rejected([
            {"url": VALID_URL, "output": "video1.mp4", "id": "video-1"},
            {"url": VALID_URL, "output": "video2.mp4", "id": "video-1"},
        ])

    def test_rejects_duplicate_output_destinations(self) -> None:
        self.assert_load_rejected([
            {"url": VALID_URL, "output": "video1.mp4"},
            {"url": VALID_URL, "output": "video1.mp4"},
        ])

    def test_accepts_safe_stable_id(self) -> None:
        downloads = self.load([
            {"url": VALID_URL, "output": "video1.mp4", "id": "video-1"},
        ])
        self.assertEqual(downloads[0]["id"], "video-1")

    def test_accepts_stable_id_at_max_length(self) -> None:
        downloads = self.load([
            {"url": VALID_URL, "output": "video1.mp4", "id": "x" * 128},
        ])
        self.assertEqual(downloads[0]["id"], "x" * 128)

    def test_rejects_unsafe_stable_ids(self) -> None:
        for item_id in ["", "a/b", "a\\b", "http://evil.com/x", "bad id"]:
            self.assert_load_rejected([
                {"url": VALID_URL, "output": "video1.mp4", "id": item_id},
            ])
        self.assert_load_rejected([
            {"url": VALID_URL, "output": "video1.mp4", "id": "x" * 129},
        ])


class ValidateOutputFilenameTests(unittest.TestCase):
    def test_returns_safe_filename(self) -> None:
        self.assertEqual(ffmpegfyMe.validate_output_filename("video1.mp4"), "video1.mp4")
        self.assertEqual(ffmpegfyMe.validate_output_filename("my video1.mp4"), "my video1.mp4")

    def test_rejects_unsafe_filenames(self) -> None:
        for filename in ["", ".", "..", "../evil.mp4", "sub/dir/video1.mp4", "/abs/video1.mp4"]:
            with self.assertRaises(SystemExit):
                ffmpegfyMe.validate_output_filename(filename)



if __name__ == "__main__":
    unittest.main()
