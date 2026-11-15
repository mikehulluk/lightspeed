"""Fast, zoomable plots of very large series.

A series is reduced once into min/max level-of-detail pyramids, cached in
an HDF5 file, and queried at the resolution the view needs.

The core - building and querying caches, and `lightspeed.view`, which says
what to draw for a view - needs only numpy and h5py, and is what any
plotting tool builds on. Drawing with matplotlib is `lightspeed.mpl`, which
needs the `mpl` extra (`pip install "lightspeed-series[mpl]"`); its
`plot_series` (the one call from a source to a zoomable plot), `ZoomSync`,
`plot_envelope` and `update_envelope_artists` can also be named from here,
and matplotlib is imported only when one of them is. `write_series` puts
arrays held in memory into a file lightspeed reads.
"""

from typing import Any

from .arraysource import ArraySource, HdfArraySource, SourceIdentity
from .cache import CacheHandle, SourceSpec, build_or_get_cache, close_cache, open_existing_cache
from .cachedir import resolve_cache_dir
from .constants import DEFAULT_CHUNK_SIZE, PLOT_SERIES_HOOK
from .exceptions import (
    CacheCorruptError,
    InvalidSourceSpecError,
    LightspeedError,
    NonMonotonicXError,
    UnsupportedQueryError,
)
from .query import QueryResult, full_x_range, query_range
from .status import StatusMap
from .view import Frame, MissingStyle, SeriesView
from .write import write_series

__all__ = [
    "ArraySource",
    "CacheCorruptError",
    "CacheHandle",
    "DEFAULT_CHUNK_SIZE",
    "Frame",
    "HdfArraySource",
    "InvalidSourceSpecError",
    "LightspeedError",
    "MissingStyle",
    "NonMonotonicXError",
    "PLOT_SERIES_HOOK",
    "QueryResult",
    "SeriesView",
    "SourceIdentity",
    "SourceSpec",
    "StatusMap",
    "UnsupportedQueryError",
    "build_or_get_cache",
    "close_cache",
    "full_x_range",
    "open_existing_cache",
    "query_range",
    "resolve_cache_dir",
    "write_series",
]

# Named here for convenience, but defined in lightspeed.mpl, which imports
# matplotlib; loading them on first use keeps `import lightspeed` free of it.
_MPL_NAMES = ("ZoomSync", "plot_envelope", "plot_series", "update_envelope_artists")


def __getattr__(name: str) -> Any:
    if name in _MPL_NAMES:
        try:
            from . import mpl
        except ModuleNotFoundError as error:
            if error.name is None or not error.name.startswith("matplotlib"):
                raise
            raise ImportError(
                f"lightspeed.{name} draws with matplotlib, which is not installed; "
                'install it with: pip install "lightspeed-series[mpl]"'
            ) from error
        return getattr(mpl, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
