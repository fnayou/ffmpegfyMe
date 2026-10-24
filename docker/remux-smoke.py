#!/usr/bin/env python3
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ffmpegfyMe


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed ({command[0]}): {detail}")
    return result


def probe(path: Path) -> dict[str, object]:
    result = run_checked([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ])
    return json.loads(result.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ffmpegfy-remux-smoke-") as directory:
        root = Path(directory)
        source = root / "source.mp4"
        run_checked([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10:duration=1",
            "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=10:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000:duration=1",
            "-map", "0:v:0", "-map", "1:v:0", "-map", "2:a:0", "-map", "3:a:0",
            "-c:v", "mpeg4", "-q:v", "8", "-c:a", "aac", "-t", "1", str(source),
        ])
        source_info = probe(source)
        source_streams = source_info["streams"]
        source_video = max((stream for stream in source_streams if stream["codec_type"] == "video"), key=lambda stream: stream["width"])
        source_audio = max((stream for stream in source_streams if stream["codec_type"] == "audio"), key=lambda stream: stream["channels"])

        handler = partial(QuietHandler, directory=str(root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/source.mp4"
            for extension, expected_format in (("mp4", "mp4"), ("mkv", "matroska")):
                output = root / f"output.{extension}"
                if not ffmpegfyMe.download_stream(url, output):
                    raise RuntimeError(f"FFmpeg failed to create {extension} output")
                info = probe(output)
                format_name = info["format"]["format_name"]
                streams = info["streams"]
                video = [stream for stream in streams if stream["codec_type"] == "video"]
                audio = [stream for stream in streams if stream["codec_type"] == "audio"]
                types = {stream["codec_type"] for stream in streams}
                if expected_format not in format_name:
                    raise RuntimeError(f"{extension} output has unexpected container: {format_name}")
                if types != {"video", "audio"} or len(streams) != 2:
                    raise RuntimeError(f"{extension} output has unexpected streams: {types}")
                if video[0]["width"] != source_video["width"] or video[0]["codec_name"] != source_video["codec_name"]:
                    raise RuntimeError(f"{extension} output did not copy the best video stream: expected video width {source_video['width']} codec {source_video['codec_name']}, actual output video width {video[0]['width']} codec {video[0]['codec_name']}")
                if audio[0]["channels"] != source_audio["channels"] or audio[0]["codec_name"] != source_audio["codec_name"]:
                    raise RuntimeError(f"{extension} output did not copy the best audio stream")
                print(f"PASS: {extension} container, best video/audio streams, stream copy")

            source_ffv1 = root / "source_ffv1.mkv"
            run_checked([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
                "-c:v", "ffv1", "-c:a", "aac", "-t", "1", str(source_ffv1),
            ])

            ffv1_url = f"http://127.0.0.1:{server.server_port}/source_ffv1.mkv"
            ffv1_output = root / "output_ffv1.mp4"
            ffv1_buffer = io.StringIO()
            with contextlib.redirect_stdout(ffv1_buffer):
                ffv1_remuxed = ffmpegfyMe.download_stream(ffv1_url, ffv1_output)
            ffv1_diagnostic = ffv1_buffer.getvalue()
            if ffv1_remuxed:
                raise RuntimeError("FFmpeg unexpectedly remuxed FFV1 source to MP4")
            ffv1_lowered = ffv1_diagnostic.lower()
            ffv1_markers = (
                "could not find tag for codec ffv1",
                "codec not currently supported in container",
            )
            if not any(marker in ffv1_lowered for marker in ffv1_markers):
                raise RuntimeError(
                    f"FFmpeg diagnostic did not identify FFV1 as unsupported by MP4 container: {ffv1_diagnostic}"
                )
            print("PASS: FFV1 source reported as unsupported by MP4 container")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
