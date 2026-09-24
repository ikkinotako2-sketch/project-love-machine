"""Checks the encoded artifact, including decoded visual and audio samples."""
import json
import os
import re
import subprocess
from fractions import Fraction
from pathlib import Path


def _run(command):
    return subprocess.run(command, check=True, text=True, capture_output=True)


def validate_video(path, expected_width=1080, expected_height=1920):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if os.path.getsize(path) < 10_000:
        raise ValueError("video file is too small")
    metadata = json.loads(_run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]).stdout)
    streams = metadata.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if not videos or not audios:
        raise ValueError("video or audio stream missing")
    video = videos[0]
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    duration = float(metadata.get("format", {}).get("duration", 0) or 0)
    fps = Fraction(video.get("avg_frame_rate", "0/1"))
    if (width, height) != (expected_width, expected_height):
        raise ValueError(f"unexpected resolution: {width}x{height}")
    if fps != 30:
        raise ValueError(f"unexpected frame rate: {fps}")
    if not 0.5 <= duration <= 180.5:
        raise ValueError(f"video duration is invalid: {duration}")
    subtitle_file = Path(path).with_name("captions.ass")
    if not subtitle_file.is_file() or "Dialogue:" not in subtitle_file.read_text(encoding="utf-8"):
        raise ValueError("timed subtitles missing")
    # One small decoded frame per 4 seconds; reject an entirely black video.
    visual = _run(["ffmpeg", "-v", "error", "-i", path, "-vf",
                   "fps=1/4,scale=32:56,signalstats,metadata=print:file=-", "-an", "-f", "null", "-"])
    luminances = [float(x) for x in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", visual.stdout)]
    if not luminances or max(luminances) < 25:
        raise ValueError("video has only dark/black frames")
    audio = _run(["ffmpeg", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"])
    level = re.search(r"mean_volume:\s*(-?[\d.]+) dB", audio.stderr)
    if not level or float(level.group(1)) < -38:
        raise ValueError("audio is silent or too quiet")
    return {"ok": True, "path": path, "bytes": os.path.getsize(path),
            "width": width, "height": height, "fps": float(fps), "duration": duration,
            "video_codec": video.get("codec_name"), "audio_codec": audios[0].get("codec_name"),
            "subtitles": True, "max_sample_luma": max(luminances), "mean_audio_db": float(level.group(1))}
