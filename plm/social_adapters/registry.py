from __future__ import annotations

from .base import SocialAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SocialAdapter] = {}

    def register(self, adapter: SocialAdapter) -> None:
        platform = adapter.platform.strip().lower()
        if not platform:
            raise ValueError("adapter platform is required")
        if platform in self._adapters:
            raise ValueError(f"adapter already registered: {platform}")
        self._adapters[platform] = adapter

    def get(self, platform: str) -> SocialAdapter:
        try:
            return self._adapters[platform]
        except KeyError as exc:
            raise KeyError(f"no adapter registered for platform: {platform}") from exc

    def platforms(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))
