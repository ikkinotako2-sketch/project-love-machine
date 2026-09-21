# PLM Pipeline Result Fetcher v1

The YouTube Pipeline publishes a sanitized result to a deterministic path on the
`plm-results` branch. This is in addition to the existing 30-day artifact, so
existing consumers remain compatible.

## Fetch URL

Replace `<job_id>` with the same ID sent to the pipeline:

```text
https://raw.githubusercontent.com/ikkinotako2-sketch/project-love-machine/plm-results/pipeline-results/<job_id>.json
```

Add a changing query string in n8n to avoid a cached response:

```text
https://raw.githubusercontent.com/ikkinotako2-sketch/project-love-machine/plm-results/pipeline-results/{{$json.job_id}}.json?ts={{$now.toMillis()}}
```

The first pipeline job creates `processing`; the final job replaces it with
`succeeded` or `failed`. A request made before the initializer finishes can
briefly return HTTP 404, so wait 10 seconds after dispatch or retry 404 once.

## Response

```json
{
  "schema_version": 1,
  "job_id": "n8n-20260921-001",
  "render_id": "n8n-20260921-001",
  "status": "succeeded",
  "video_id": "abc123",
  "youtube_status": "private",
  "youtube_url": "https://www.youtube.com/watch?v=abc123",
  "failed_stage": null,
  "error": null
}
```

Failure responses use `status: failed` and include only the allowlisted error
fields `stage`, `type`, `code`, and `message`. Internal stage payloads, OAuth
tokens, cookies, and GitHub Secrets are never written to the results branch.

## n8n

Use one HTTP Request node per check:

- Method: `GET`
- Authentication: `None`
- Response Format: `JSON`
- URL: the cache-busted URL above

Branch on `status`: wait and check again for `processing`, continue on
`succeeded`, and route `failed_stage` plus `error` to error handling on `failed`.
