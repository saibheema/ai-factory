from collections import defaultdict

import httpx

# Rolling compression settings
_MAX_BANK_SIZE: int = 30      # trigger compression when a bank reaches this size
_COMPRESS_KEEP_LAST: int = 15  # keep this many recent items after compression


class MemoryController:
    """Phase 1 local in-memory implementation with rolling compression."""

    def __init__(
        self,
        max_bank_size: int = _MAX_BANK_SIZE,
        compress_keep_last: int = _COMPRESS_KEEP_LAST,
    ) -> None:
        self._banks: dict[str, list[str]] = defaultdict(list)
        self._max_bank_size = max_bank_size
        self._compress_keep_last = compress_keep_last

    def recall(self, bank_id: str, limit: int = 5) -> list[str]:
        return self._banks[bank_id][-limit:]

    def retain(self, bank_id: str, item: str) -> None:
        self._banks[bank_id].append(item)
        # Trigger rolling compression if the bank exceeds the size limit
        if len(self._banks[bank_id]) > self._max_bank_size:
            self._compress(bank_id)

    def _compress(self, bank_id: str) -> None:
        """Keep the most recent items and prepend a compression marker."""
        current = self._banks[bank_id]
        removed = len(current) - self._compress_keep_last
        if removed <= 0:
            return
        kept = current[-self._compress_keep_last:]
        marker = f"[COMPRESSED: {removed} older items removed]"
        self._banks[bank_id] = [marker] + kept

    def compress(self, bank_id: str, keep_last: int | None = None) -> dict:
        """Manually compress a bank. Returns compression stats."""
        keep = keep_last if keep_last is not None else self._compress_keep_last
        current = self._banks[bank_id]
        before = len(current)
        if before <= keep:
            return {"action": "skipped", "items_before": before, "items_removed": 0, "items_after": before}
        self._banks[bank_id] = current[-keep:]
        removed = before - keep
        return {"action": "compressed", "items_before": before, "items_removed": removed, "items_after": keep}

    def snapshot(self) -> dict[str, list[str]]:
        return dict(self._banks)


class RemoteMemoryController:
    """Phase 1 remote memory client with local fallback and compression support."""

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

    def search(self, bank_id: str, query: str, limit: int = 5) -> list[str]:
        """Semantic / text search over a bank — calls the /search endpoint."""
        try:
            response = httpx.get(
                f"{self.base_url}/banks/{bank_id}/search",
                params={"q": query, "limit": limit},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("results", [])
        except Exception:
            # Fallback: substring match over local fallback bank
            q_lower = query.lower()
            items = self._fallback.recall(bank_id, limit=200)
            return [i for i in items if q_lower in i.lower()][:limit]

    def compress(self, bank_id: str, keep_last: int = 15) -> dict:
        """Trigger compression on the remote memory service."""
        try:
            response = httpx.post(
                f"{self.base_url}/banks/{bank_id}/compress",
                params={"keep_last": keep_last},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return self._fallback.compress(bank_id, keep_last=keep_last)

    def stats(self, bank_id: str) -> dict:
        """Return size and metadata for a bank."""
        try:
            response = httpx.get(
                f"{self.base_url}/banks/{bank_id}/stats",
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            items = self._fallback.recall(bank_id, limit=1000)
            return {"bank_id": bank_id, "count": len(items), "store": "memory-fallback"}
