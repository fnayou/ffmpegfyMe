import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from urllib.request import ProxyHandler, Request, build_opener
from unittest import mock

import ffmpegfyMe


PLAYLIST_PATH = "/playlist.m3u8"
SEGMENT_PATH = "/segment.ts"
PLAYLIST_BODY = (
    "#EXTM3U\n"
    "#EXT-X-VERSION:3\n"
    "#EXTINF:2.0,\n"
    "segment.ts\n"
    "#EXT-X-ENDLIST\n"
)
FAKE_TOKEN = "tok"
FAKE_COOKIE = "session=abc123"
REQUEST_TIMEOUT_SECONDS = 5


class LocalHLSFixtureServer(ThreadingHTTPServer):
    """In-process HTTP server exposing the local authenticated HLS fixture routes."""

    allow_reuse_address = True

    def __init__(self, address: Any, handler: Any) -> None:
        super().__init__(address, handler)
        self.request_log: List[Tuple[str, bool]] = []

    def record_request(self, path: str, authenticated: bool) -> None:
        self.request_log.append((path, authenticated))


class LocalHLSFixtureHandler(BaseHTTPRequestHandler):
    """Minimal HLS fixture handler requiring auth for playlist and segment routes."""

    server_version = "ffmpegfyMeLocalHLSFixture/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        """Silence default stderr logging for the in-process fixture server."""

    def _respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_authenticated(self) -> bool:
        return bool(self.headers.get("Authorization")) and bool(self.headers.get("Cookie"))

    def do_GET(self) -> None:
        authenticated = self._is_authenticated()
        self.server.record_request(self.path, authenticated)
        if not authenticated:
            self._respond(401, "text/plain", b"unauthorized")
            return
        if self.path == PLAYLIST_PATH:
            self._respond(200, "application/vnd.apple.mpegurl", PLAYLIST_BODY.encode("utf-8"))
            return
        if self.path == SEGMENT_PATH:
            self._respond(200, "video/mp2t", b"\x00\x00\x00\x00\x00\x00\x00\x00")
            return
        self._respond(404, "text/plain", b"not found")


class LocalHLSFakeFFmpegRunner:
    """Fake FFmpeg subprocess runner standing in for the real FFmpeg binary.

    Consumes the FFmpeg command built by the app (input URL plus auth options),
    replays the authenticated HLS fetch against the in-process local fixture
    server, follows the relative segment URI, and returns success only when both
    the playlist and segment routes answered 200. Does not execute real FFmpeg.
    """

    def __init__(self) -> None:
        self.commands: List[List[str]] = []
        self.playlist_status: Optional[int] = None
        self.segment_status: Optional[int] = None
        self.playlist_url: Optional[str] = None
        self.segment_url: Optional[str] = None

    def __call__(self, command: List[str], on_output=None) -> int:
        self.commands.append(list(command))
        return self._fetch_authenticated_hls(command)

    def _fetch_authenticated_hls(self, command: List[str]) -> int:
        cmd = list(command)
        if "-i" not in cmd:
            return 1
        input_url = cmd[cmd.index("-i") + 1]
        headers = self._auth_headers_from_command(cmd)
        opener = build_opener(ProxyHandler({}))
        playlist_status, playlist_body = self._get(opener, input_url, headers)
        self.playlist_status = playlist_status
        self.playlist_url = input_url
        if playlist_status != 200 or playlist_body is None:
            return 1
        segment_uri = self._segment_uri_from_playlist(playlist_body)
        if not segment_uri:
            return 1
        segment_url = urljoin(input_url, segment_uri)
        segment_status, _ = self._get(opener, segment_url, headers)
        self.segment_status = segment_status
        self.segment_url = segment_url
        return 0 if segment_status == 200 else 1

    @staticmethod
    def _auth_headers_from_command(command: List[str]) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if "-headers" in command:
            headers_value = command[command.index("-headers") + 1]
            for line in headers_value.split("\r\n"):
                name, _, value = line.partition(":")
                name = name.strip()
                if name:
                    headers[name] = value.strip()
        if "-cookies" in command:
            cookies = command[command.index("-cookies") + 1]
            if cookies:
                headers["Cookie"] = cookies.split(";", 1)[0]
        return headers

    @staticmethod
    def _segment_uri_from_playlist(playlist_body: str) -> Optional[str]:
        for line in playlist_body.splitlines():
            candidate = line.strip()
            if candidate and not candidate.startswith("#"):
                return candidate
        return None

    def _get(self, opener: Any, url: str, headers: Dict[str, str]) -> Tuple[int, Optional[str]]:
        request = Request(url, headers=headers)
        try:
            with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return response.status, response.read().decode("utf-8")
        except Exception:
            return 500, None


class LocalHLSFixtureTests(unittest.TestCase):
    """Local fixture test: app-generated auth config vs in-process authenticated HLS server."""

    def setUp(self) -> None:
        self.server = LocalHLSFixtureServer(("127.0.0.1", 0), LocalHLSFixtureHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self._stop_server)
        host, port = self.server.server_address[0], self.server.server_address[1]
        self.base_url = f"http://{host}:{port}"
        self.output_path = Path("out") / "hls_fixture_video.mp4"

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)

    def _auth_item(self) -> Dict[str, Any]:
        return {
            "url": f"{self.base_url}{PLAYLIST_PATH}",
            "output": "hls_fixture_video.mp4",
            "headers": {"Authorization": "${API_TOKEN}"},
            "cookies": "${SESSION_ID}",
        }

    def test_download_with_retry_succeeds_when_local_auth_hls_fixture_accepts_requests(self) -> None:
        """Check app-generated auth config against local fixture; no real FFmpeg."""
        fake = LocalHLSFakeFFmpegRunner()
        with mock.patch.dict(os.environ, {"API_TOKEN": FAKE_TOKEN, "SESSION_ID": FAKE_COOKIE}):
            success = ffmpegfyMe.download_with_retry(self._auth_item(), self.output_path, runner=fake)
        self.assertTrue(success)
        self.assertEqual(len(fake.commands), 1)
        cmd = fake.commands[0]
        self.assertEqual(cmd[cmd.index("-i") + 1], f"{self.base_url}{PLAYLIST_PATH}")
        self.assertEqual(cmd[cmd.index("-headers") + 1], f"Authorization: {FAKE_TOKEN}")
        self.assertEqual(cmd[cmd.index("-cookies") + 1], FAKE_COOKIE)
        self.assertEqual(fake.playlist_status, 200)
        self.assertEqual(fake.segment_status, 200)
        self.assertEqual(fake.segment_url, f"{self.base_url}{SEGMENT_PATH}")
        self.assertEqual(
            self.server.request_log,
            [(PLAYLIST_PATH, True), (SEGMENT_PATH, True)],
        )
