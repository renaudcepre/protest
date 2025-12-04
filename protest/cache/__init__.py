"""Cache module for ProTest."""

from protest.cache.plugin import CachePlugin
from protest.cache.storage import CacheStorage, TestCacheEntry

__all__ = ["CachePlugin", "CacheStorage", "TestCacheEntry"]
