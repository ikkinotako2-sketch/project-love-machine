from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


SUPPORTED_PLATFORMS = frozenset(
    {
        "youtube",
        "bluesky",
        "twitch",
        "twitcasting",
        "note",
        "patreon",
        "tiktok",
        "instagram",
        "x",
    }
)

_ACCOUNT_ID_RE = re.compile(
    r"^(?P<platform>youtube|bluesky|twitch|twitcasting|note|patreon|"
    r"tiktok|instagram|x)_[a-z0-9][a-z0-9-]*(?:_[a-z0-9][a-z0-9-]*)*_[0-9]{3}$"
)
_CREDENTIAL_REF_RE = re.compile(
    r"^(?:n8n|github-secret|env)://[A-Za-z0-9_.:/-]+$"
)
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "cookie",
    "cookies",
    "client_secret",
    "private_key",
    "secret",
}


class AccountConfigError(ValueError):
    """Raised when an account configuration is unsafe or invalid."""


def _find_inline_secret(value: Any, path: str = "account") -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            next_path = f"{path}.{key}"
            if normalized in _SECRET_KEYS:
                return next_path
            found = _find_inline_secret(nested, next_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found = _find_inline_secret(nested, f"{path}[{index}]")
            if found:
                return found
    return None


@dataclass(frozen=True)
class PostingPolicy:
    daily_limit: int = 1
    min_interval_seconds: int = 3600
    max_retries: int = 2
    timezone: str = "Asia/Tokyo"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PostingPolicy":
        data = data or {}
        policy = cls(
            daily_limit=int(data.get("daily_limit", 1)),
            min_interval_seconds=int(data.get("min_interval_seconds", 3600)),
            max_retries=int(data.get("max_retries", 2)),
            timezone=str(data.get("timezone", "Asia/Tokyo")),
        )
        if not 0 <= policy.daily_limit <= 100:
            raise AccountConfigError("daily_limit must be between 0 and 100")
        if not 0 <= policy.min_interval_seconds <= 604800:
            raise AccountConfigError(
                "min_interval_seconds must be between 0 and 604800"
            )
        if not 0 <= policy.max_retries <= 5:
            raise AccountConfigError("max_retries must be between 0 and 5")
        if not policy.timezone.strip():
            raise AccountConfigError("timezone is required")
        return policy


@dataclass(frozen=True)
class AccountConfig:
    account_id: str
    platform: str
    display_name: str
    credential_ref: str
    enabled: bool = False
    posting_policy: PostingPolicy = field(default_factory=PostingPolicy)
    adapter_config: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "adapter_config", MappingProxyType(dict(self.adapter_config))
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AccountConfig":
        secret_path = _find_inline_secret(data)
        if secret_path:
            raise AccountConfigError(
                f"inline secret field is forbidden: {secret_path}; use credential_ref"
            )

        required = ("account_id", "platform", "display_name", "credential_ref")
        missing = [key for key in required if not str(data.get(key, "")).strip()]
        if missing:
            raise AccountConfigError(f"missing required fields: {', '.join(missing)}")

        account_id = str(data["account_id"]).strip().lower()
        platform = str(data["platform"]).strip().lower()
        match = _ACCOUNT_ID_RE.fullmatch(account_id)
        if not match:
            raise AccountConfigError(
                "account_id must match <platform>_<genre>_<number>, for example "
                "youtube_game_001"
            )
        if platform not in SUPPORTED_PLATFORMS:
            raise AccountConfigError(f"unsupported platform: {platform}")
        if match.group("platform") != platform:
            raise AccountConfigError("account_id platform prefix must match platform")

        credential_ref = str(data["credential_ref"]).strip()
        if not _CREDENTIAL_REF_RE.fullmatch(credential_ref):
            raise AccountConfigError(
                "credential_ref must use n8n://, github-secret://, or env://"
            )

        tags_value = data.get("tags") or []
        if not isinstance(tags_value, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags_value
        ):
            raise AccountConfigError("tags must be a list of non-empty strings")

        adapter_config = data.get("adapter_config") or {}
        if not isinstance(adapter_config, Mapping):
            raise AccountConfigError("adapter_config must be an object")

        return cls(
            account_id=account_id,
            platform=platform,
            display_name=str(data["display_name"]).strip(),
            credential_ref=credential_ref,
            enabled=bool(data.get("enabled", False)),
            posting_policy=PostingPolicy.from_dict(data.get("posting_policy")),
            adapter_config=adapter_config,
            tags=tuple(tag.strip() for tag in tags_value),
        )
