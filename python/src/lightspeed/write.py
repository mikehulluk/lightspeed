"""Writing arrays held in memory into an HDF5 file lightspeed can read."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np

from .cache import SourceSpec
from .exceptions import InvalidSourceSpecError, NonMonotonicXError

# Rows per HDF5 chunk: large enough that a streaming pass over the file reads
# in big blocks, small enough that a short series is not padded far past its
# length.
WRITE_CHUNK_ROWS = 1 << 16


def write_series(
    path: str | Path,
    y: Any,
    x: Any = None,
    *,
    x0: float = 0.0,
    dx: float = 1.0,
    y_dataset: str = "/y",
    x_dataset: str = "/x",
) -> SourceSpec:
    """Writes `y` (and `x`, if given) to a new HDF5 file at `path` and
    returns the `SourceSpec` that reads it back.

    Without `x` the series is uniform, sample i at `x0 + i * dx`. With `x`
    it is irregular, sample i at `x0 + x[i] * dx`; `x` must be
    non-decreasing, as every irregular series must, so a series that steps
    backwards fails here, where it is written, rather than when its cache is
    first built. Both are stored as float64, chunked for streaming.
    """

    y_values = np.asarray(y, dtype=np.float64)
    if y_values.ndim != 1:
        raise InvalidSourceSpecError(f"y must be 1-D, got shape {y_values.shape}")
    x_values = None
    if x is not None:
        x_values = np.asarray(x, dtype=np.float64)
        if x_values.shape != y_values.shape:
            raise InvalidSourceSpecError(f"x has shape {x_values.shape} but y has {y_values.shape}")
        steps_back = np.flatnonzero(x_values[1:] < x_values[:-1])
        if steps_back.size:
            raise NonMonotonicXError(
                f"x is not sorted: sample {int(steps_back[0]) + 1} is less than the one before it; "
                "a series' x must be non-decreasing"
            )

    path = Path(path)
    chunks = (min(len(y_values), WRITE_CHUNK_ROWS),) if len(y_values) else None
    with h5py.File(path, "w") as handle:
        handle.create_dataset(y_dataset, data=y_values, chunks=chunks)
        if x_values is not None:
            handle.create_dataset(x_dataset, data=x_values, chunks=chunks)

    if x_values is None:
        return SourceSpec.uniform(path, y_dataset, x0=x0, dx=dx)
    return SourceSpec.irregular(path, y_dataset, x_dataset, x0=x0, dx=dx)
