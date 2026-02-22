from collections import defaultdict

import httpx


class MemoryController:
    """Phase 1 local memory implementation."""

    def __init__(self) -> None:
        self._banks: dict[str, list[str]] = defaultdict(list)

    def recall(self, bank_id: str, limit: int = 5) -> list[str]:
        return self._banks[bank_id][-limit:]

    def retain(self, bank_id: str, item: str) -> None:
        self._banks[bank_id].append(item)

    def snapshot(self) -> dict[str, list[str]]:
        return dict(self._banks)


class RemoteMemoryController:
    """Phase 1 remote memory client with local fallback."""

    def __init__(self, base_url: str, timeout: float = 3.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._fallback = MemoryController()

    def recall(self, bank_id: str, limit: int = 5) -> list[str]:
        try:
            response = httpx.get(
                f"{self.base_url}/banks/{bank_id}/recall",
                params={"limit": limit},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("items", [])
        except Exception:
            return self._fallback.recall(bank_id, limit)

    def retain(self, bank_id: str, item: str) -> None:
        try:
            response = httpx.post(
                f"{self.base_url}/banks/{bank_id}/retain",
                json={"item": item},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return
        except Exception:
            self._fallback.retain(bank_id, item)

    def snapshot(self) -> dict[str, list[str]]:
        try:
            response = httpx.get(f"{self.base_url}/banks/snapshot", timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            return payload.get("banks", {})
        except Exception:
            return self._fallback.snapshot()
