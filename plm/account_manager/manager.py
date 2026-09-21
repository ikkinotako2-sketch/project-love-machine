from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import AccountConfig, AccountConfigError, SUPPORTED_PLATFORMS


class AccountManager:
    """Validated, O(1) account registry shared by every PLM workflow."""

    def __init__(
        self,
        accounts: Iterable[AccountConfig],
        *,
        max_accounts: int = 100,
    ) -> None:
        if max_accounts < 1:
            raise AccountConfigError("max_accounts must be positive")
        account_list = list(accounts)
        if len(account_list) > max_accounts:
            raise AccountConfigError(
                f"account count {len(account_list)} exceeds limit {max_accounts}"
            )

        self._accounts: dict[str, AccountConfig] = {}
        for account in account_list:
            if account.account_id in self._accounts:
                raise AccountConfigError(
                    f"duplicate account_id: {account.account_id}"
                )
            self._accounts[account.account_id] = account
        self.max_accounts = max_accounts

    @classmethod
    def from_file(
        cls, path: str | Path, *, max_accounts: int = 100
    ) -> "AccountManager":
        with Path(path).open(encoding="utf-8") as file:
            document = json.load(file)
        if not isinstance(document, dict) or not isinstance(
            document.get("accounts"), list
        ):
            raise AccountConfigError("config root must contain an accounts list")
        accounts = [AccountConfig.from_dict(item) for item in document["accounts"]]
        return cls(accounts, max_accounts=max_accounts)

    def get(self, account_id: str) -> AccountConfig:
        try:
            return self._accounts[account_id]
        except KeyError as exc:
            raise KeyError(f"unknown account_id: {account_id}") from exc

    def list_accounts(
        self, *, platform: str | None = None, enabled_only: bool = False
    ) -> tuple[AccountConfig, ...]:
        if platform is not None and platform not in SUPPORTED_PLATFORMS:
            raise AccountConfigError(f"unsupported platform: {platform}")
        accounts = self._accounts.values()
        return tuple(
            account
            for account in accounts
            if (platform is None or account.platform == platform)
            and (not enabled_only or account.enabled)
        )

    def __len__(self) -> int:
        return len(self._accounts)
