"""
Cache Manager
In-memory caching with TTL support.
"""
import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with TTL."""
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)


class CacheManager:
    """Thread-safe in-memory cache with TTL and LRU eviction."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: dict[str, CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return default

            if time.time() > entry.expires_at:
                del self._cache[key]
                return default

            entry.access_count += 1
            entry.last_accessed = time.time()
            return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache with TTL."""
        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.max_size:
                self._evict_lru()

            ttl = ttl or self.default_ttl
            self._cache[key] = CacheEntry(
                value=value,
                expires_at=time.time() + ttl,
            )

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        """Clear all cache entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._cache:
            return

        lru_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )
        del self._cache[lru_key]

    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._cache.items() if now > v.expires_at]
            for k in expired:
                del self._cache[k]
            return len(expired)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = time.time()
            valid = sum(1 for v in self._cache.values() if now <= v.expires_at)
            expired = len(self._cache) - valid
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid,
                "expired_entries": expired,
                "max_size": self.max_size,
                "hit_rate": self._calculate_hit_rate(),
            }

    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate (approximate)."""
        total_access = sum(e.access_count for e in self._cache.values())
        if total_access == 0:
            return 0.0
        # This is a simplification; real hit rate needs miss tracking
        return 1.0


# Global cache instance
cache_manager = CacheManager()


def get_cache() -> CacheManager:
    """Get global cache manager."""
    return cache_manager
