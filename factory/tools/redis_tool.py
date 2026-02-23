"""Redis tool — cache and queue operations for live services.

Used by sre_ops and devops for cache inspection, key analysis,
health checks, and pub/sub monitoring.

Env vars:
  REDIS_URL      — redis://[:password@]host:port[/db] (default: redis://localhost:6379/0)
  REDIS_TIMEOUT  — socket timeout seconds (default: 5)
"""

import logging
import os

log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TIMEOUT = int(os.getenv("REDIS_TIMEOUT", "5"))


def _client():
    try:
        import redis
        return redis.Redis.from_url(REDIS_URL, socket_timeout=TIMEOUT, decode_responses=True)
    except ImportError:
        raise RuntimeError("redis not installed — pip install redis")


def ping() -> dict:
    """Check Redis connectivity.

    Returns:
      {"reachable": bool, "latency_ms": float, "error": str|None}
    """
    import time
    try:
        client = _client()
        start = time.monotonic()
        ok = client.ping()
        latency = round((time.monotonic() - start) * 1000, 2)
        return {"reachable": ok, "latency_ms": latency, "error": None}
    except Exception as e:
        return {"reachable": False, "latency_ms": -1, "error": str(e)}


def get_info() -> dict:
    """Return Redis SERVER + MEMORY + STATS info.

    Returns:
      {"success": bool, "version": str, "memory_used_mb": float,
       "connected_clients": int, "uptime_seconds": int, "ops_per_sec": int,
       "keyspace": dict, "error": str|None}
    """
    try:
        client = _client()
        info = client.info()
        keyspace = client.info("keyspace")
        return {
            "success": True,
            "version": info.get("redis_version", ""),
            "memory_used_mb": round(info.get("used_memory", 0) / 1e6, 2),
            "memory_peak_mb": round(info.get("used_memory_peak", 0) / 1e6, 2),
            "connected_clients": info.get("connected_clients", 0),
            "uptime_seconds": info.get("uptime_in_seconds", 0),
            "ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
            "evicted_keys": info.get("evicted_keys", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "keyspace": keyspace,
            "error": None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get(key: str) -> dict:
    """Get a key value.

    Returns:
      {"found": bool, "value": any, "ttl_seconds": int, "type": str}
    """
    try:
        client = _client()
        key_type = client.type(key)
        if key_type == "none":
            return {"found": False, "value": None, "ttl_seconds": -2, "type": "none"}
        ttl = client.ttl(key)
        value: object
        if key_type == "string":
            value = client.get(key)
        elif key_type == "list":
            value = client.lrange(key, 0, -1)
        elif key_type == "set":
            value = list(client.smembers(key))
        elif key_type == "hash":
            value = client.hgetall(key)
        elif key_type == "zset":
            value = client.zrange(key, 0, -1, withscores=True)
        else:
            value = str(client.dump(key))
        return {"found": True, "value": value, "ttl_seconds": ttl, "type": key_type}
    except Exception as e:
        return {"found": False, "value": None, "ttl_seconds": -1, "type": "", "error": str(e)}


def set(key: str, value: str, ttl_seconds: int = 0) -> dict:
    """Set a string key.

    Returns:
      {"success": bool, "error": str|None}
    """
    try:
        client = _client()
        if ttl_seconds > 0:
            client.setex(key, ttl_seconds, value)
        else:
            client.set(key, value)
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete(key: str) -> dict:
    """Delete a key.

    Returns:
      {"deleted": bool, "error": str|None}
    """
    try:
        client = _client()
        n = client.delete(key)
        return {"deleted": n > 0, "error": None}
    except Exception as e:
        return {"deleted": False, "error": str(e)}


def list_keys(pattern: str = "*", max_keys: int = 200) -> dict:
    """Scan keys matching a pattern (uses SCAN, not KEYS, for safety).

    Args:
      pattern:  Redis glob pattern e.g. "session:*", "cache:user:*"
      max_keys: Maximum keys to return (default 200)

    Returns:
      {"success": bool, "keys": list[str], "count": int, "error": str|None}
    """
    try:
        client = _client()
        keys = []
        cursor = 0
        while True:
            cursor, batch = client.scan(cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0 or len(keys) >= max_keys:
                break
        return {"success": True, "keys": keys[:max_keys], "count": len(keys), "error": None}
    except Exception as e:
        return {"success": False, "keys": [], "count": 0, "error": str(e)}


def flush_pattern(pattern: str) -> dict:
    """Delete all keys matching a pattern.

    Returns:
      {"deleted_count": int, "error": str|None}
    """
    try:
        client = _client()
        keys = []
        cursor = 0
        while True:
            cursor, batch = client.scan(cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        if keys:
            deleted = client.delete(*keys)
        else:
            deleted = 0
        log.info("Flushed %d keys matching '%s'", deleted, pattern)
        return {"deleted_count": deleted, "error": None}
    except Exception as e:
        return {"deleted_count": 0, "error": str(e)}
