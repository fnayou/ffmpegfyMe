import os
import tempfile
import unittest
from pathlib import Path
from typing import Callable, Dict, List, Optional
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
        if self.exit_code == 0 and Path(command[-1]).suffix.lower() in (".mp4", ".mkv"):
            Path(command[-1]).write_bytes(b"fake-output")
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
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.output_path = Path(self._temp_dir.name) / "video1.mp4"

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
        self.assertEqual(cmd[2], "-protocol_whitelist")
        self.assertEqual(cmd[3], "http,https,tcp,tls,crypto")
        self.assertEqual(cmd[4], "-i")
        self.assertEqual(cmd[5], self.url)
        self.assertNotEqual(Path(cmd[-1]), self.output_path)
        self.assertEqual(Path(cmd[-1]).parent, self.output_path.parent)
        self.assertEqual(Path(cmd[-1]).suffix, self.output_path.suffix)

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


class TestDownloadStreamCommandConstruction(unittest.TestCase):
    """download_stream must build a constrained authenticated FFmpeg input command."""

    ALLOWED_PROTOCOLS = "http,https,tcp,tls,crypto"

    def setUp(self) -> None:
        self.url = "https://cdn.example.com/video1.m3u8"
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.output_path = Path(self._temp_dir.name) / "video1.mp4"

    def _build_command(self, headers: Optional[Dict[str, str]] = None, cookies: Optional[str] = None) -> List[str]:
        fake = FakeFFmpegRunner(exit_code=0)
        success = ffmpegfyMe.download_stream(
            self.url,
            self.output_path,
            runner=fake,
            headers=headers,
            cookies=cookies,
        )
        self.assertTrue(success)
        self.assertEqual(len(fake.commands), 1)
        return fake.commands[0]

    def test_no_auth_command_constrains_protocols_before_input(self) -> None:
        cmd = self._build_command()
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertEqual(cmd[1], "-y")
        self.assertEqual(cmd[2], "-protocol_whitelist")
        self.assertEqual(cmd[3], self.ALLOWED_PROTOCOLS)
        self.assertEqual(cmd[4], "-i")
        self.assertEqual(cmd[5], self.url)
        self.assertNotEqual(Path(cmd[-1]), self.output_path)
        self.assertEqual(Path(cmd[-1]).parent, self.output_path.parent)
        self.assertEqual(Path(cmd[-1]).suffix, self.output_path.suffix)

    def test_no_auth_command_omits_auth_options(self) -> None:
        cmd = self._build_command()
        self.assertNotIn("-headers", cmd)
        self.assertNotIn("-cookies", cmd)

    def test_auth_command_passes_headers_and_cookies_before_input(self) -> None:
        cmd = self._build_command(
            headers={"Authorization": "Bearer real-token"},
            cookies="session=real-session",
        )
        self.assertEqual(cmd[cmd.index("-protocol_whitelist") + 1], self.ALLOWED_PROTOCOLS)
        self.assertEqual(cmd[cmd.index("-headers") + 1], "Authorization: Bearer real-token")
        self.assertEqual(cmd[cmd.index("-cookies") + 1], "session=real-session")
        self.assertLess(cmd.index("-protocol_whitelist"), cmd.index("-i"))
        self.assertLess(cmd.index("-headers"), cmd.index("-i"))
        self.assertLess(cmd.index("-cookies"), cmd.index("-i"))

    def test_headers_formatted_as_crlf_separated_name_value_lines(self) -> None:
        cmd = self._build_command(
            headers={"Authorization": "Bearer tok", "X-Custom-Header": "custom-value"},
            cookies=None,
        )
        self.assertEqual(
            cmd[cmd.index("-headers") + 1],
            "Authorization: Bearer tok\r\nX-Custom-Header: custom-value",
        )

    def test_protocol_whitelist_excludes_disallowed_protocols(self) -> None:
        cmd = self._build_command()
        whitelist = cmd[cmd.index("-protocol_whitelist") + 1]
        protocols = whitelist.split(",")
        self.assertIn("http", protocols)
        self.assertIn("https", protocols)
        self.assertIn("tcp", protocols)
        self.assertIn("tls", protocols)
        self.assertIn("crypto", protocols)
        self.assertNotIn("file", protocols)
        self.assertNotIn("ftp", protocols)
        self.assertNotIn("data", protocols)

    def test_command_stream_copies_without_bsf_map_or_data_and_keeps_extension(self) -> None:
        for output_name in ("video1.mp4", "video1.mkv"):
            with self.subTest(output_name=output_name):
                output_path = Path(self._temp_dir.name) / output_name
                fake = FakeFFmpegRunner(exit_code=0)
                self.assertTrue(ffmpegfyMe.download_stream(self.url, output_path, runner=fake))
                self.assertEqual(len(fake.commands), 1)
                cmd = fake.commands[0]
                self.assertEqual(cmd[cmd.index("-c") + 1], "copy")
                self.assertIn("-sn", cmd)
                self.assertIn("-dn", cmd)
                self.assertNotIn("-map", cmd)
                self.assertNotIn("-bsf:a", cmd)
                self.assertNotIn("aac_adtstoasc", cmd)
                self.assertNotEqual(Path(cmd[-1]), output_path)
                self.assertEqual(Path(cmd[-1]).parent, output_path.parent)
                self.assertEqual(Path(cmd[-1]).suffix, output_path.suffix)


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


class TestDownloadWithRetryAuthWiring(unittest.TestCase):
    """download_with_retry must resolve environment auth before the retry loop."""

    def setUp(self) -> None:
        self.url = "https://cdn.example.com/video1.m3u8"
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.output_path = Path(self._temp_dir.name) / "video1.mp4"

    def _auth_item(self, header_value: str = "${API_TOKEN}", cookies: Optional[str] = None) -> Dict[str, str]:
        item: Dict[str, str] = {
            "url": self.url,
            "output": "video1.mp4",
            "headers": {"Authorization": header_value},
        }
        if cookies is not None:
            item["cookies"] = cookies
        return item

    def test_configured_env_values_reach_runner_args(self) -> None:
        item = {
            "url": self.url,
            "output": "video1.mp4",
            "headers": {"Authorization": "${API_TOKEN}"},
            "cookies": "${SESSION_ID}",
        }
        fake = FakeFFmpegRunner(exit_code=0)
        with mock.patch.dict(os.environ, {"API_TOKEN": "tok", "SESSION_ID": "session=abc"}):
            self.assertTrue(ffmpegfyMe.download_with_retry(item, self.output_path, runner=fake))
        self.assertEqual(len(fake.commands), 1)
        cmd = fake.commands[0]
        self.assertEqual(cmd[cmd.index("-headers") + 1], "Authorization: tok")
        self.assertEqual(cmd[cmd.index("-cookies") + 1], "session=abc")

    def test_missing_env_value_returns_false_before_runner_and_without_retry_sleep(self) -> None:
        item = self._auth_item()
        fake = FakeFFmpegRunner(exit_code=0)
        with mock.patch.dict(os.environ) as env:
            env.pop("API_TOKEN", None)
            with mock.patch("ffmpegfyMe.time.sleep") as sleep:
                self.assertFalse(
                    ffmpegfyMe.download_with_retry(item, self.output_path, runner=fake, max_retries=2)
                )
        self.assertEqual(len(fake.commands), 0)
        sleep.assert_not_called()

    def test_empty_env_value_returns_false_before_runner_and_without_retry_sleep(self) -> None:
        item = self._auth_item()
        fake = FakeFFmpegRunner(exit_code=0)
        with mock.patch.dict(os.environ, {"API_TOKEN": ""}):
            with mock.patch("ffmpegfyMe.time.sleep") as sleep:
                self.assertFalse(
                    ffmpegfyMe.download_with_retry(item, self.output_path, runner=fake, max_retries=2)
                )
        self.assertEqual(len(fake.commands), 0)
        sleep.assert_not_called()

    def test_no_auth_item_passes_unauthenticated_command_to_runner(self) -> None:
        item = {"url": self.url, "output": "video1.mp4"}
        fake = FakeFFmpegRunner(exit_code=0)
        self.assertTrue(ffmpegfyMe.download_with_retry(item, self.output_path, runner=fake))
        self.assertEqual(len(fake.commands), 1)
        cmd = fake.commands[0]
        self.assertNotIn("-headers", cmd)
        self.assertNotIn("-cookies", cmd)

    def test_retry_backoff_uses_jittered_sleeps(self) -> None:
        item = _make_item()
        fake = FakeFFmpegRunner(exit_code=1)
        with mock.patch("random.uniform", side_effect=[2.0, 6.0]) as uniform:
            with mock.patch("ffmpegfyMe.time.sleep") as sleep:
                self.assertFalse(ffmpegfyMe.download_with_retry(item, self.output_path, runner=fake))
        self.assertEqual(len(fake.commands), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2.0, 6.0])
        self.assertEqual(uniform.call_count, 2)


if __name__ == "__main__":
    unittest.main()