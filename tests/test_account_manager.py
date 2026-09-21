import json
import tempfile
import unittest
from pathlib import Path

from plm.account_manager import (
    SUPPORTED_PLATFORMS,
    AccountConfig,
    AccountConfigError,
    AccountManager,
)


def account_data(index: int, platform: str = "youtube") -> dict:
    return {
        "account_id": f"{platform}_game_{index:03d}",
        "platform": platform,
        "display_name": f"Account {index}",
        "credential_ref": f"n8n://{platform}_game_{index:03d}",
        "enabled": index % 2 == 0,
    }


class AccountManagerTests(unittest.TestCase):
    def test_accepts_one_hundred_unique_accounts(self):
        manager = AccountManager(
            AccountConfig.from_dict(account_data(index))
            for index in range(1, 101)
        )
        self.assertEqual(len(manager), 100)
        self.assertEqual(len(manager.list_accounts(enabled_only=True)), 50)

    def test_rejects_more_than_one_hundred_accounts(self):
        with self.assertRaisesRegex(AccountConfigError, "exceeds limit"):
            AccountManager(
                AccountConfig.from_dict(account_data(index))
                for index in range(1, 102)
            )

    def test_rejects_duplicate_account_id(self):
        account = AccountConfig.from_dict(account_data(1))
        with self.assertRaisesRegex(AccountConfigError, "duplicate account_id"):
            AccountManager([account, account])

    def test_rejects_platform_mismatch(self):
        data = account_data(1)
        data["platform"] = "bluesky"
        with self.assertRaisesRegex(AccountConfigError, "prefix must match"):
            AccountConfig.from_dict(data)

    def test_rejects_inline_secrets_recursively(self):
        data = account_data(1)
        data["adapter_config"] = {"oauth": {"access_token": "do-not-commit"}}
        with self.assertRaisesRegex(AccountConfigError, "inline secret"):
            AccountConfig.from_dict(data)

    def test_loads_example_shape_from_file(self):
        document = {"accounts": [account_data(1), account_data(2, "bluesky")]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounts.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            manager = AccountManager.from_file(path)
        self.assertEqual(manager.get("youtube_game_001").platform, "youtube")
        self.assertEqual(len(manager.list_accounts(platform="bluesky")), 1)

    def test_platform_manifest_covers_all_supported_platforms(self):
        manifest_path = Path(__file__).parents[1] / "config/platforms/platforms.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["platforms"]), SUPPORTED_PLATFORMS)
        self.assertEqual(
            set(manifest["implementation_status"]), SUPPORTED_PLATFORMS
        )


if __name__ == "__main__":
    unittest.main()
