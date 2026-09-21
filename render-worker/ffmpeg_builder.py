import json
import os
import subprocess


DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def _probe_duration(path: str) -> float:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ]
    )
    data = json.loads(result.stdout)
    return max(0.1, float(data["format"]["duration"]))


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds >= 100:
        whole += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{whole:02d}.{centiseconds:02d}"


def _escape_ass(text: str) -> str:
    return (
        str(text)
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _write_ass(captions: list[dict], path: str, width: int, height: int) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Shorts,Noto Sans CJK JP,76,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,2,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for caption in captions:
        start = caption.get("start_seconds", caption.get("start", 0))
        end = caption.get("end_seconds", caption.get("end", float(start) + 1.5))
        text = caption.get("text", caption.get("caption", ""))
        if not str(text).strip():
            continue
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Shorts,,0,0,0,,{_escape_ass(text)}\n"
        )

    with open(path, "w", encoding="utf-8") as file:
        file.writelines(lines)


def build_video(
    payload: dict,
    audio_path: str = "audio.wav",
    output_path: str = "short.mp4",
) -> str:
    output = payload.get("output") or {}
    width = int(output.get("width", DEFAULT_WIDTH))
    height = int(output.get("height", DEFAULT_HEIGHT))
    fps = int(output.get("fps", DEFAULT_FPS))

    captions = payload.get("captions") or []
    if not captions:
        captions = [
            {
                "index": i + 1,
                "start_seconds": scene.get("start", 0),
                "end_seconds": scene.get("end", 1.5),
                "text": scene.get("caption", ""),
            }
            for i, scene in enumerate(payload.get("scenes") or [])
        ]

    audio_duration = _probe_duration(audio_path)
    scene_ends = [
        float(scene.get("end", 0))
        for scene in (payload.get("scenes") or [])
        if scene.get("end") is not None
    ]
    caption_ends = [
        float(caption.get("end_seconds", caption.get("end", 0)))
        for caption in captions
        if caption.get("end_seconds", caption.get("end")) is not None
    ]
    duration = max([audio_duration, *scene_ends, *caption_ends, 1.0])

    ass_path = "captions.ass"
    _write_ass(captions, ass_path, width, height)

    font_dir = "/usr/share/fonts/opentype/noto"
    subtitles_filter = f"subtitles={ass_path}"
    if os.path.isdir(font_dir):
        subtitles_filter += f":fontsdir={font_dir}"

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x101018:s={width}x{height}:r={fps}:d={duration}",
        "-i",
        audio_path,
        "-vf",
        subtitles_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        output_path,
    ]

    result = _run(command)
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 10_000:
        raise RuntimeError(
            "FFmpeg did not create a valid-looking MP4. stderr: " + result.stderr[-2000:]
        )

    return output_path
