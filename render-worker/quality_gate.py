import json
import os
import subprocess


def _probe(path: str) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            path,
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def validate_video(
    path: str,
    expected_width: int = 1080,
    expected_height: int = 1920,
) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if os.path.getsize(path) < 10_000:
        raise ValueError("video file is too small")

    metadata = _probe(path)
    streams = metadata.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]

    if not video_streams:
        raise ValueError("video stream missing")
    if not audio_streams:
        raise ValueError("audio stream missing")

    video = video_streams[0]
    width = int(video.get("width", 0))
    height = int(video.get("height", 0))
    duration = float(metadata.get("format", {}).get("duration", 0) or 0)

    if width != expected_width or height != expected_height:
        raise ValueError(
            f"unexpected resolution: {width}x{height}, "
            f"expected {expected_width}x{expected_height}"
        )
    if duration <= 0.2:
        raise ValueError("video duration is invalid")

    return {
        "ok": True,
        "path": path,
        "bytes": os.path.getsize(path),
        "width": width,
        "height": height,
        "duration": duration,
        "video_codec": video.get("codec_name"),
        "audio_codec": audio_streams[0].get("codec_name"),
    }
