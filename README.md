# Project Love Machine (PLM)

AI-assisted SNS automation platform.

## What this repository is

Project Love Machine is the shared automation foundation for:

- YouTube Shorts
- Bluesky
- Twitch / TwitCasting LIVE
- note
- Patreon
- future TikTok / Instagram / X adapters

The goal is to reuse one common engine instead of building a separate system for every account.

## Current working component

### PLM Render Cloud

Current flow:

```
n8n
→ PLM Render Request
→ GitHub Actions
→ VOICEVOX
→ FFmpeg
→ Quality Gate
→ MP4
```

A first PC-free 1080x1920 H.264/AAC render has already completed successfully on GitHub Actions.

## Architecture

- **n8n**: orchestration and schedules
- **GitHub**: source of truth, Actions, render jobs, tests, version history
- **PLM Render Cloud**: cloud video generation
- **Social Adapters**: platform-specific posting
- **PLM Account Manager**: multi-account configuration
- **PLM Improvement Engine**: performance-driven iteration
- **PLM Trend Radar**: content/editing trend monitoring
- **PLM Tool Radar**: GitHub OSS / MOGE technology discovery
- **PLM Command Center**: status, errors, performance and revenue dashboard

See [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md) for the complete naming map and roadmap.

## Security

- Never commit API keys or access tokens
- Store credentials in n8n Credentials or GitHub Secrets
- Keep platform adapters isolated from the common core
