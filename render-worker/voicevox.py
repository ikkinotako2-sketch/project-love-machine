import json
import urllib.parse
import urllib.request


VOICEVOX_BASE_URL = "http://127.0.0.1:50021"


def _post(url: str, body: bytes = b"", content_type: str | None = None) -> bytes:
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def generate_voice(
    narration: str,
    speaker: int = 1,
    output_path: str = "audio.wav",
    speed_scale: float = 1.08,
) -> str:
    if not narration or not narration.strip():
        raise ValueError("narration is empty")

    query_params = urllib.parse.urlencode(
        {"text": narration, "speaker": int(speaker)}
    )
    query_raw = _post(f"{VOICEVOX_BASE_URL}/audio_query?{query_params}")
    query = json.loads(query_raw.decode("utf-8"))

    # Slightly faster pacing works well for short-form narration while
    # preserving natural phrasing. This can later be moved to a style profile.
    query["speedScale"] = float(speed_scale)

    synthesis_params = urllib.parse.urlencode({"speaker": int(speaker)})
    audio = _post(
        f"{VOICEVOX_BASE_URL}/synthesis?{synthesis_params}",
        json.dumps(query, ensure_ascii=False).encode("utf-8"),
        "application/json",
    )

    if len(audio) < 1024:
        raise RuntimeError("VOICEVOX returned an unexpectedly small audio file")

    with open(output_path, "wb") as file:
        file.write(audio)

    return output_path
