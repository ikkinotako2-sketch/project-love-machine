"""Self-contained Shorts backgrounds; no external footage or downloaded assets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30
PALETTES = [
    ("#17435C", "#2C7890", "#F5B863"),
    ("#49366B", "#7861A4", "#E6A7CF"),
    ("#235748", "#428A72", "#D9C982"),
    ("#604336", "#A36F56", "#F1C48B"),
    ("#253D70", "#597BAD", "#A8D3DF"),
    ("#613D61", "#A66A8D", "#E6BC9D"),
]
ASSET_ROOT = Path(__file__).resolve().parent / "assets" / "audio"


def _run(command):
    return subprocess.run(command, check=True, text=True, capture_output=True)


def _probe_duration(path):
    data = json.loads(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path]).stdout)
    return max(0.1, float(data["format"]["duration"]))


def _ass_time(seconds):
    centiseconds = max(0, round(float(seconds) * 100))
    hours, rest = divmod(centiseconds, 360000)
    minutes, rest = divmod(rest, 6000)
    whole, rest = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{rest:02d}"


def _escape_ass(value):
    return str(value).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _caption_text(caption):
    raw = str(caption.get("text", caption.get("caption", "")))
    words = caption.get("emphasis_words", caption.get("emphasis", []))
    if isinstance(words, str):
        words = [words]
    if not isinstance(words, list):
        words = []
    words = [w for w in words if isinstance(w, str) and 1 <= len(w) <= 30 and w in raw]
    # Apply tags only after escaping user text, so user-supplied ASS tags stay inert.
    parts = []
    position = 0
    while position < len(raw):
        match = next((w for w in sorted(words, key=len, reverse=True) if raw.startswith(w, position)), None)
        if match:
            parts.append(r"{\c&H00D7FF&\fs78}" + _escape_ass(match) + r"{\c&HFFFFFF&\fs68}")
            position += len(match)
        else:
            parts.append(_escape_ass(raw[position]))
            position += 1
    return "".join(parts)


def _write_ass(captions, path, width, height):
    margin = round(height * 0.22)  # Keep text above the Shorts controls and bottom caption area.
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Shorts,Noto Sans CJK JP,68,&H00FFFFFF,&H000000FF,&H00192331,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,110,190,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    count = 0
    for caption in captions:
        start = float(caption.get("start_seconds", caption.get("start", 0)))
        end = float(caption.get("end_seconds", caption.get("end", start + 1.5)))
        if end <= start or not str(caption.get("text", caption.get("caption", ""))).strip():
            continue
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Shorts,,0,0,0,,{_caption_text(caption)}\n")
        count += 1
    Path(path).write_text("".join(lines), encoding="utf-8")
    return count


def _asset_path(config):
    """Only explicitly bundled, licensed audio can enter the render."""
    if not isinstance(config, dict) or not config.get("asset"):
        return None
    name = config["asset"]
    if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith((".wav", ".mp3", ".ogg")):
        return None
    path = ASSET_ROOT / name
    # Sidecar documents provenance and license for each bundled sound.
    if path.is_file() and path.with_name(name + ".license.txt").is_file():
        return str(path)
    return None


def _captions_with_scene_emphasis(captions, scenes):
    """Copy emphasis only from the scene that supplied this timed caption."""
    result = []
    for caption in captions:
        if not isinstance(caption, dict):
            continue
        merged = dict(caption)
        if not merged.get("emphasis_words") and not merged.get("emphasis"):
            text = str(merged.get("text", merged.get("caption", "")))
            start = float(merged.get("start_seconds", merged.get("start", 0)))
            end = float(merged.get("end_seconds", merged.get("end", start + 1.5)))
            for scene in scenes:
                if (isinstance(scene, dict) and text == str(scene.get("caption", ""))
                        and abs(start - float(scene.get("start", -1))) < 0.05
                        and abs(end - float(scene.get("end", -1))) < 0.05):
                    merged["emphasis_words"] = scene.get("emphasis_words", scene.get("emphasis", []))
                    break
        result.append(merged)
    return result


def _fit_captions_to_audio(captions, scenes, audio_duration):
    """Stretch generated scene captions when the narration outlasts their timeline."""
    if not captions or not any(isinstance(s, dict) for s in scenes):
        return captions
    first = min(float(c.get("start_seconds", c.get("start", 0))) for c in captions)
    last = max(float(c.get("end_seconds", c.get("end", 0))) for c in captions)
    scene_last = max(float(s.get("end", 0)) for s in scenes if isinstance(s, dict))
    # Only normalize a complete scene/caption timeline starting at zero. Leave
    # independently timed subtitles alone and preserve the original wording.
    if (first > 0.05 or last <= 0 or abs(scene_last - last) > 0.05
            or audio_duration <= last + 0.1):
        return captions
    factor = audio_duration / last
    fitted = []
    for caption in captions:
        updated = dict(caption)
        updated["start_seconds"] = float(caption.get("start_seconds", caption.get("start", 0))) * factor
        updated["end_seconds"] = float(caption.get("end_seconds", caption.get("end", 0))) * factor
        fitted.append(updated)
    return fitted


def _visual_filters(keyword, base, accent, highlight):
    """Draw simple, local pixel-art motifs; unknown keywords retain v1 backgrounds."""
    key = keyword.lower()
    rain = any(word in key for word in ("rain", "storm", "shower", "雨", "嵐"))
    cloud = rain or any(word in key for word in ("cloud", "sky", "雲", "空"))
    sun = any(word in key for word in ("sun", "solar", "sunset", "太陽", "晴れ", "夕日"))
    night = any(word in key for word in ("night", "moon", "star", "夜", "月", "星"))
    study = any(word in key for word in ("study", "book", "desk", "note", "勉強", "本", "ノート"))
    if not (cloud or sun or night or study):
        return (f"drawbox=x=80:y=110:w=980:h=460:color={accent}@0.75:t=fill,"
                f"drawbox=x=260:y=630:w=780:h=700:color={highlight}@0.24:t=fill,"
                f"drawbox=x=100:y=1450:w=760:h=310:color={accent}@0.55:t=fill,")
    shapes = []
    def box(x, y, w, h, color):
        shapes.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={color}:t=fill")
    if night:
        for x, y in ((180, 260), (860, 280), (680, 720), (230, 850), (945, 630)):
            box(x, y, 24, 24, "0xFBE9A6")
        box(710, 330, 170, 170, "0xFBE9A6")
        box(760, 290, 160, 160, base)  # Stepped crescent.
    if sun:
        box(720, 200, 170, 170, "0xFFD166")
        for x, y, w, h in ((790, 155, 25, 35), (790, 380, 25, 35),
                            (670, 275, 35, 25), (905, 275, 35, 25)):
            box(x, y, w, h, "0xFFD166")
    if cloud:
        for x, y, w, h in ((390, 430, 350, 160), (305, 515, 520, 145),
                            (250, 600, 640, 140)):
            box(x, y, w, h, "0xF2F6F7")
        if rain:
            for x in (330, 445, 560, 675, 790):
                box(x, 780 + (x % 3) * 40, 22, 160, "0x83CDF2")
    if study:
        box(230, 840, 700, 36, "0xC69A72")  # Desk.
        box(315, 450, 245, 340, "0xF2F0E7")  # Two open book pages.
        box(575, 450, 245, 340, "0xF2F0E7")
        box(560, 445, 14, 350, "0xA88A78")
        for y in (525, 585, 645, 705):
            box(355, y, 165, 9, "0xA5BAC4")
            box(615, y, 165, 9, "0xA5BAC4")
    box(100, 1450, 760, 310, f"{accent}@0.55")
    return ",".join(shapes) + ","


def _segments(scenes, duration):
    ordered = sorted((s for s in scenes if isinstance(s, dict)), key=lambda s: float(s.get("start", 0)))[:24]
    segments = []
    cursor = 0.0
    for scene in ordered:
        start = min(duration, max(cursor, float(scene.get("start", cursor))))
        end = min(duration, max(start, float(scene.get("end", start))))
        if start > cursor + 0.02:
            segments.append((cursor, start, {"visual_keyword": "neutral"}))
        if end > start + 0.02:
            segments.append((start, end, scene))
        cursor = max(cursor, end)
    if cursor < duration - 0.02:
        segments.append((cursor, duration, {"visual_keyword": "neutral"}))
    return segments or [(0, duration, {"visual_keyword": "neutral"})]


def build_video(payload, audio_path="audio.wav", output_path="short.mp4"):
    # The publishing contract always remains 1080x1920 / 30fps.
    output = payload.get("output") or {}
    if (int(output.get("width", DEFAULT_WIDTH)), int(output.get("height", DEFAULT_HEIGHT)), int(output.get("fps", DEFAULT_FPS))) != (1080, 1920, 30):
        raise ValueError("Shorts output must be 1080x1920 at 30fps")
    scenes = payload.get("scenes") or []
    captions = payload.get("captions") or [
        {"start_seconds": s.get("start", 0), "end_seconds": s.get("end", 1.5),
         "text": s.get("caption", ""), "emphasis_words": s.get("emphasis_words", s.get("emphasis", []))}
        for s in scenes if isinstance(s, dict)
    ]
    captions = _captions_with_scene_emphasis(captions, scenes)
    audio_duration = _probe_duration(audio_path)
    duration = max([audio_duration, 1.0] +
                   [float(s.get("end", 0)) for s in (payload.get("scenes") or []) if isinstance(s, dict)] +
                   [float(c.get("end_seconds", c.get("end", 0))) for c in captions if isinstance(c, dict)])
    if duration > 180:
        raise ValueError("render duration exceeds 180 seconds")
    captions = _fit_captions_to_audio(captions, scenes, audio_duration)
    if not _write_ass(captions, "captions.ass", 1080, 1920):
        raise ValueError("no timed subtitles")
    subtitle_filter = "subtitles=captions.ass"
    if os.path.isdir("/usr/share/fonts/opentype/noto"):
        subtitle_filter += ":fontsdir=/usr/share/fonts/opentype/noto"

    command = ["ffmpeg", "-y", "-i", audio_path]
    bgm = _asset_path(payload.get("bgm"))
    if bgm:
        command += ["-stream_loop", "-1", "-i", bgm]
    sfx = _asset_path(payload.get("sfx") or (payload.get("bgm") or {}).get("sfx"))
    if sfx:
        command += ["-i", sfx]
    filters = []
    labels = []
    previous_palette = None
    for i, (start, end, scene) in enumerate(_segments(payload.get("scenes") or [], duration)):
        key = str(scene.get("visual_keyword") or "neutral")[:120]
        palette_index = int.from_bytes(hashlib.sha256(key.encode()).digest()[:2], "big") % len(PALETTES)
        if palette_index == previous_palette:
            palette_index = (palette_index + 1) % len(PALETTES)
        previous_palette = palette_index
        palette = PALETTES[palette_index]
        base, accent, highlight = [c.replace("#", "0x") for c in palette]
        frames = max(1, round((end - start) * 30))
        span = frames / 30
        # Keep the existing crop motion and fades after drawing the keyword motif.
        filters.append(
            f"color=c={base}:s=1152x2048:r=30:d={span},"
            f"{_visual_filters(key, base, accent, highlight)}"
            "crop=1080:1920:x='36+24*sin(t/2)':y='64+32*sin(t/3)',"
            f"fade=t=in:st=0:d={min(0.12, span/4)},"
            f"fade=t=out:st={max(0, span-0.12)}:d={min(0.12, span/4)},"
            f"trim=duration={span},setpts=PTS-STARTPTS[v{i}]"
        )
        labels.append(f"[v{i}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0,{subtitle_filter},format=yuv420p[v]")
    filters.append(f"[0:a]loudnorm=I=-16:TP=-2:LRA=9,apad,atrim=duration={duration}[voice]")
    mix = "[voice]"
    if bgm:
        filters.append(f"[1:a]volume=0.10,atrim=duration={duration},asetpts=PTS-STARTPTS[bgm]")
        filters.append("[voice][bgm]amix=inputs=2:duration=first:normalize=0[music]")
        mix = "[music]"
    if sfx:
        index = 2 if bgm else 1
        filters.append(f"[{index}:a]volume=0.12,adelay=250|250,atrim=duration={duration}[fx]")
        filters.append(f"{mix}[fx]amix=inputs=2:duration=first:normalize=0[a]")
        mix = "[a]"
    command += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", mix,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                "-r", "30", "-c:a", "aac", "-b:a", "192k", "-t", str(duration),
                "-movflags", "+faststart", output_path]
    result = _run(command)
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 10_000:
        raise RuntimeError("FFmpeg did not create a valid-looking MP4. stderr: " + result.stderr[-2000:])
    return output_path
