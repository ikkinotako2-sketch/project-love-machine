from __future__ import annotations

import threading

from plm.social_adapters.errors import PermanentAdapterError


class QuotaBudget:
    """Process-local admission guard for documented YouTube API quota buckets."""

    def __init__(self, *, upload_limit: int = 100, data_units: int = 10_000) -> None:
        if upload_limit < 1 or data_units < 1:
            raise ValueError("quota limits must be positive")
        self.upload_limit = upload_limit
        self.data_units = data_units
        self._uploads = 0
        self._data_units = 0
        self._lock = threading.Lock()

    def consume_upload(self) -> None:
        with self._lock:
            if self._uploads >= self.upload_limit:
                raise PermanentAdapterError(
                    "local YouTube upload quota guard reached",
                    code="youtube_upload_quota_guard",
                )
            self._uploads += 1

    def consume_data_units(self, units: int = 1) -> None:
        if units < 1:
            raise ValueError("quota units must be positive")
        with self._lock:
            if self._data_units + units > self.data_units:
                raise PermanentAdapterError(
                    "local YouTube Data API quota guard reached",
                    code="youtube_data_quota_guard",
                )
            self._data_units += units

    @property
    def usage(self) -> dict[str, int]:
        with self._lock:
            return {"uploads": self._uploads, "data_units": self._data_units}
