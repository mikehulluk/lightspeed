class LightspeedError(Exception):
    """Base error for every error lightspeed raises."""


class InvalidSourceSpecError(LightspeedError):
    """Raised when a SourceSpec is internally inconsistent."""


class NonMonotonicXError(InvalidSourceSpecError):
    """Raised when an irregular x array is not sorted, which the cache relies on."""


class CacheCorruptError(LightspeedError):
    """Raised when an on-disk cache file fails its sanity check."""


class UnsupportedQueryError(LightspeedError):
    """Raised when a query cannot be answered (e.g. invalid range)."""
