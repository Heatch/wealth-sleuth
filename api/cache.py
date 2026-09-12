"""Thread-safe in-memory TTL cache for portfolio computations."""

import time
from threading import Lock


class PortfolioCache:
    """TTL cache with manual invalidation.

    Caches expensive computations (valuation series, price maps) that only
    change when batch scripts run. Default TTL is 5 minutes.
    """

    def __init__(self, default_ttl: float = 300.0):
        self._data = {}
        self._timestamps = {}
        self._lock = Lock()
        self._default_ttl = default_ttl

    def get(self, key: str, ttl: float = None):
        with self._lock:
            if key in self._data:
                age = time.time() - self._timestamps[key]
                limit = ttl if ttl is not None else self._default_ttl
                if age < limit:
                    return self._data[key]
                del self._data[key]
                del self._timestamps[key]
        return None

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value
            self._timestamps[key] = time.time()

    def invalidate(self, key: str = None):
        """Invalidate a specific key, a prefix, or everything."""
        with self._lock:
            if key is None:
                self._data.clear()
                self._timestamps.clear()
            elif key.endswith("*"):
                prefix = key[:-1]
                for k in [k for k in self._data if k.startswith(prefix)]:
                    del self._data[k]
                    del self._timestamps[k]
            else:
                self._data.pop(key, None)
                self._timestamps.pop(key, None)

    def invalidate_on_consolidate(self):
        """Clear caches that depend on transaction data."""
        self.invalidate("valuation_*")
        self.invalidate("holdings_*")

    def invalidate_on_price_update(self):
        """Clear caches that depend on price data."""
        self.invalidate("valuation_*")
        self.invalidate("price_map")


# Global cache instance
cache = PortfolioCache()
