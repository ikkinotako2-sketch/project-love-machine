# PLM Social Adapter Specification v1.0

## Purpose

Every SNS integration plugs into one shared execution model:

```
PLM common engine
  + AccountConfig
  + platform SocialAdapter
```

No workflow is copied per account. A new account is a validated configuration entry. A
new platform is one adapter implementation registered for that platform.

## Account boundary

`account_id` follows `<platform>_<genre>_<number>` such as
`youtube_game_001`. Credentials are never stored in the account JSON. Only a reference
is allowed:

- `n8n://<credential-name>`
- `github-secret://<secret-name>`
- `env://<variable-name>`

All accounts default to `enabled: false`. Enabling an account is a separate operational
approval after its platform authentication and policy checks are complete.

## Required adapter contract

Each adapter inherits `SocialAdapter` and declares `AdapterCapabilities`.

| Operation | Contract | Required behavior |
|---|---|---|
| Publish | `publish(account, request)` | Return `PostResult`, including platform post ID when available |
| Schedule | `schedule(account, request)` | Implement only after official support is verified; otherwise raise `UnsupportedOperationError` |
| Status | `get_post_status(account, post_id)` | Normalize platform state to `PostState` |
| Analytics | `get_analytics(account, post_id)` | Normalize common metrics and preserve platform-only fields in `raw` |
| Errors | typed adapter exceptions | Separate transient, permanent, and unsupported failures |

## Common processing

`SocialHub` owns behavior that must not be reimplemented in every adapter:

1. Resolve `account_id` through `AccountManager`.
2. Refuse disabled accounts.
3. Select the adapter by platform.
4. Claim an idempotency fingerprint before delivery.
5. Call immediate or scheduled delivery.
6. Retry only `TransientAdapterError` within bounded policy limits.
7. Store success/failure state and block duplicate pending/successful deliveries.

Production deployments must replace the in-memory idempotency reference store with a
durable transactional store before running multiple workers. The interface and tests
remain the same.

## Platform-specific boundary

Adapters alone may contain:

- official API endpoints and request formats
- OAuth/token refresh behavior through an external credential reference
- platform media upload steps
- platform status mapping
- platform analytics mapping
- documented rate-limit interpretation

Adapters must not contain account scheduling policy, cross-platform retries, content
generation, or duplicate-prevention rules.

## Capability verification rule

`config/platforms/platforms.json` intentionally marks integrations as
`not_connected` or `future`. Do not set a capability to true or add network code until
the platform's current official documentation, account eligibility, age requirements,
cost, and terms have been checked. This prevents guessed integrations from silently
publishing or incurring fees.

## Secret handling

- Never commit tokens, cookies, passwords, private keys, webhook secrets, or OAuth
  client secrets.
- Keep secrets in n8n Credentials or GitHub Secrets.
- Account configuration contains only credential references.
- `AccountConfig` rejects common inline secret field names recursively.

## Adding an account

1. Create credentials outside GitHub.
2. Add a disabled account entry based on `accounts.example.json`.
3. Validate and test the adapter with a non-public dry run where supported.
4. Perform one explicitly approved live test.
5. Enable the account only after the post ID, status, and idempotency record agree.

## Adding a platform

1. Verify official documentation, pricing, account/age rules, and scheduling support.
2. Implement a `SocialAdapter` subclass without changing `SocialHub`.
3. Add contract tests for publish, scheduling, status, analytics, errors, and retries.
4. Store no credentials in the repository.
5. Update the platform manifest and this document with verified capabilities.
