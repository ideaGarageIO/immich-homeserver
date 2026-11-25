"""Minimal Immich REST client (the endpoints this tool needs)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class CheckResult:
    id: str
    action: str  # "accept" (not on server) | "reject"
    reason: str | None = None  # "duplicate" | "unsupported-format"
    asset_id: str | None = None
    is_trashed: bool = False


class ImmichClient:
    def __init__(self, url: str, api_key: str, timeout: float = 60.0, transport=None):
        self.base = url.rstrip("/") + "/api"
        self._client = httpx.Client(
            headers={"x-api-key": api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def ping(self) -> bool:
        r = self._client.get(f"{self.base}/server/ping")
        r.raise_for_status()
        return r.json().get("res") == "pong"

    def version(self) -> str:
        r = self._client.get(f"{self.base}/server/version")
        r.raise_for_status()
        v = r.json()
        return f"{v['major']}.{v['minor']}.{v['patch']}"

    def me(self) -> dict:
        r = self._client.get(f"{self.base}/users/me")
        r.raise_for_status()
        return r.json()

    def bulk_upload_check(self, items: list[tuple[str, str]]) -> list[CheckResult]:
        """items: (client id, hex sha1). Returns one result per item.

        Never send an empty list: Immich v3 answers it with HTTP 500.
        """
        if not items:
            return []
        payload = {"assets": [{"id": i, "checksum": c} for i, c in items]}
        r = self._client.post(f"{self.base}/assets/bulk-upload-check", json=payload)
        r.raise_for_status()
        return [
            CheckResult(
                id=x["id"],
                action=x["action"],
                reason=x.get("reason"),
                asset_id=x.get("assetId"),
                is_trashed=bool(x.get("isTrashed", False)),
            )
            for x in r.json()["results"]
        ]
