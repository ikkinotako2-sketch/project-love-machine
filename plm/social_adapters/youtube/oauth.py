from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from plm.social_adapters.errors import PermanentAdapterError, TransientAdapterError


class EnvironmentOAuthTokenProvider:
    """Refresh a Google OAuth token from one JSON-valued environment secret."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(
        self,
        env_name: str = "PLM_YOUTUBE_OAUTH_JSON",
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.env_name = env_name
        self._opener = opener
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0

    def get_access_token(self) -> str:
        if self._token and self._clock() < self._expires_at - 60:
            return self._token
        bundle = self._load_bundle()
        form = urllib.parse.urlencode(
            {
                "client_id": bundle["client_id"],
                "client_secret": bundle["client_secret"],
                "refresh_token": bundle["refresh_token"],
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.TOKEN_URL,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504}:
                raise TransientAdapterError(
                    "temporary Google OAuth service error",
                    code=f"oauth_http_{exc.code}",
                ) from exc
            raise PermanentAdapterError(
                f"Google OAuth refresh was rejected: HTTP {exc.code}: {body[:200]}",
                code="oauth_refresh_rejected",
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransientAdapterError(
                "temporary Google OAuth connection failure",
                code="oauth_connection_error",
            ) from exc
        except (ValueError, KeyError) as exc:
            raise PermanentAdapterError(
                "Google OAuth response was invalid",
                code="oauth_invalid_response",
            ) from exc

        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise PermanentAdapterError(
                "Google OAuth response did not contain an access token",
                code="oauth_missing_access_token",
            )
        self._token = token
        self._expires_at = self._clock() + int(payload.get("expires_in", 3600))
        return token

    def _load_bundle(self) -> dict[str, str]:
        raw = os.environ.get(self.env_name)
        if not raw:
            raise PermanentAdapterError(
                f"OAuth credential environment variable is missing: {self.env_name}",
                code="oauth_credentials_missing",
            )
        try:
            bundle = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PermanentAdapterError(
                "OAuth credential secret must be a JSON object",
                code="oauth_credentials_invalid",
            ) from exc
        required = ("client_id", "client_secret", "refresh_token")
        if not isinstance(bundle, dict) or any(
            not isinstance(bundle.get(key), str) or not bundle[key]
            for key in required
        ):
            raise PermanentAdapterError(
                "OAuth credential secret is missing required fields",
                code="oauth_credentials_invalid",
            )
        return bundle
