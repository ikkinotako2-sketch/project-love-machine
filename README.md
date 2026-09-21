# Project Love Machine

Cloud-first automation core for AI-assisted short-form video production and social distribution.

## Goals

- Run without a local Windows PC
- Use GitHub Actions as the cloud render worker
- Receive structured V2 payloads from n8n
- Generate narration, subtitles, motion, BGM/SFX, and MP4
- Add quality checks before upload
- Keep secrets out of the repository

## Planned flow

n8n → Cloud Render Payload → GitHub Actions → VOICEVOX/FFmpeg → Quality Gate → MP4 → social upload
