import json
import os
import traceback

from ffmpeg_builder import build_video
from quality_gate import validate_video
from voicevox import generate_voice


RESULT_PATH = "render-result.json"


def _write_result(payload: dict) -> None:
    with open(RESULT_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _json_env(name: str, default):
    value = os.environ.get(name)
    if not value:
        return default
    return json.loads(value)


def load_payload() -> dict:
    output = _json_env(
        "INPUT_OUTPUT_JSON",
        {"format": "mp4", "width": 1080, "height": 1920, "fps": 30},
    )

    return {
        "title": os.environ.get("INPUT_TITLE", ""),
        "hook": os.environ.get("INPUT_HOOK", ""),
        "narration": os.environ.get("INPUT_NARRATION", ""),
        "speaker": int(os.environ.get("INPUT_SPEAKER", "1")),
        "scenes": _json_env("INPUT_SCENES_JSON", []),
        "captions": _json_env("INPUT_CAPTIONS_JSON", []),
        "bgm": _json_env("INPUT_BGM_JSON", {}),
        "output": output,
    }


def main():
    stage = "render_request"
    stages = {
        "render_request": "pending",
        "voice": "pending",
        "render": "pending",
        "quality_gate": "pending",
    }
    try:
        payload = load_payload()
        if not payload["narration"].strip():
            raise ValueError("narration is required")
        with open("payload_snapshot.json", "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        stages["render_request"] = "succeeded"

        stage = "voice"
        audio_path = generate_voice(
            payload["narration"],
            payload["speaker"],
            output_path="audio.wav",
        )
        stages["voice"] = "succeeded"

        stage = "render"
        video_path = build_video(
            payload, audio_path=audio_path, output_path="short.mp4"
        )
        stages["render"] = "succeeded"

        stage = "quality_gate"
        output = payload["output"]
        report = validate_video(
            video_path,
            expected_width=int(output.get("width", 1080)),
            expected_height=int(output.get("height", 1920)),
        )
        stages["quality_gate"] = "succeeded"
        result = {"ok": True, "stages": stages, "quality_gate": report}
        _write_result(result)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as exc:
        stages[stage] = "failed"
        _write_result(
            {
                "ok": False,
                "stages": stages,
                "error": {
                    "stage": stage,
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        )
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
