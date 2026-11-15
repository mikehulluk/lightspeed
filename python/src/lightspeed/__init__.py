"""Fast, zoomable plots of very large series.

A series is reduced once into min/max level-of-detail pyramids, cached in
an HDF5 file, and queried at the resolution the view needs.
"""

from .arraysource import ArraySource, HdfArraySource, SourceIdentity
from .cache import CacheHandle, SourceSpec, build_or_get_cache, close_cache, open_existing_cache
from .cachedir import resolve_cache_dir
from .constants import DEFAULT_CHUNK_SIZE
from .exceptions import (
    CacheCorruptError,
    InvalidSourceSpecError,
    NonMonotonicXError,
    LightspeedError,
    UnsupportedQueryError,
)
from .mpl import ZoomSync, plot_envelope, update_envelope_artists
from .query import QueryResult, full_x_range, query_range

__all__ = [
    "ArraySource",
    "CacheCorruptError",
    "CacheHandle",
    "DEFAULT_CHUNK_SIZE",
    "HdfArraySource",
    "InvalidSourceSpecError",
    "NonMonotonicXError",
    "LightspeedError",
    "QueryResult",
    "SourceIdentity",
    "SourceSpec",
    "UnsupportedQueryError",
    "ZoomSync",
    "build_or_get_cache",
    "close_cache",
    "full_x_range",
    "open_existing_cache",
    "plot_envelope",
    "query_range",
    "resolve_cache_dir",
    "update_envelope_artists",
]
