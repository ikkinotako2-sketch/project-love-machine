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

## Implemented common core

### PLM Account Manager

The initial account registry is implemented in `plm/account_manager/`.

- validated IDs such as `youtube_game_001`
- YouTube, Bluesky, Twitch, TwitCasting, note, Patreon and future platform IDs
- one account configuration per account instead of one copied workflow
- O(1) account lookup and a validated 100-account limit
- disabled-by-default accounts and bounded posting policies
- credential references only; common inline secret fields are rejected

Start from `config/accounts/accounts.example.json`. Keep real credentials in n8n
Credentials or GitHub Secrets.

### PLM Social Hub / Adapter Contract

The common adapter contract is implemented in `plm/social_adapters/`.

- publish and optional scheduling
- normalized post IDs and states
- normalized analytics snapshots
- typed permanent/transient errors
- bounded transient retries
- idempotency-based duplicate prevention
- platform adapter registry

See [docs/SOCIAL_ADAPTER_SPEC.md](docs/SOCIAL_ADAPTER_SPEC.md). Platform network
integrations remain disabled until current official API, pricing, eligibility and policy
requirements are verified.

See [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md) for the complete naming map and roadmap.

### PLM YouTube Adapter v1

The first real platform adapter is implemented in `plm/social_adapters/youtube/`.

- official YouTube Data API resumable video upload
- private-by-default immediate upload and verified `publishAt` scheduling
- normalized video ID, upload/processing status, and analytics
- transient-only retry classification and conservative quota guards
- one shared Adapter for every `youtube_*_NNN` account
- n8n-callable GitHub Actions entrypoint in `youtube-adapter.yml`
- cross-run upload claims plus SocialHub idempotency protection

The implementation is tested with mocks and has completed one real-account private
upload. See [docs/YOUTUBE_ADAPTER_V1.md](docs/YOUTUBE_ADAPTER_V1.md).

### PLM YouTube Pipeline v1

`youtube-pipeline.yml` gives n8n one dispatch entrypoint for Render Request, Render
Cloud, Quality Gate, YouTube upload, and normalized results. It reuses both existing
workflows through `workflow_call`; n8n supplies only one `job_id` and never supplies a
Render Run ID or artifact name. The final artifact is `pipeline-result-<job_id>`. YouTube results are handed to the
final job through the existing `youtube-result-<run_id>` artifact, not through a
secret-tainted reusable-workflow output.

See [docs/YOUTUBE_PIPELINE_V1.md](docs/YOUTUBE_PIPELINE_V1.md) for the n8n JSON contract.

### PLM Pipeline Result Fetcher v1

The Pipeline writes a sanitized result to
`plm-results/pipeline-results/<job_id>.json`: `processing` at startup and the
final `succeeded` or `failed` result at completion. n8n can fetch it with one
HTTP GET using only `job_id`; no Actions Run ID or Artifact ID lookup is needed.
The existing `pipeline-result-<job_id>` artifact remains available.

See [docs/PIPELINE_RESULT_FETCHER_V1.md](docs/PIPELINE_RESULT_FETCHER_V1.md).

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

The independent `Test PLM Core` workflow tests the shared core without modifying or
executing PLM Render Cloud.

## Security

- Never commit API keys or access tokens
- Store credentials in n8n Credentials or GitHub Secrets
- Keep platform adapters isolated from the common core
