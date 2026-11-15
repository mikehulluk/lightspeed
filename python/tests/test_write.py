from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from lightspeed import NonMonotonicXError, build_or_get_cache, query_range, write_series
from lightspeed.exceptions import InvalidSourceSpecError


def test_a_uniform_series_reads_back_on_its_grid(tmp_path: Path) -> None:
    y = np.sin(np.linspace(0.0, 10.0, 5000))
    spec = write_series(tmp_path / "s.h5", y, x0=2.0, dx=0.5)

    assert not spec.irregular_x
    handle = build_or_get_cache(spec, cache_dir=tmp_path / "cache")
    result = query_range(handle, spec, 2.0, 2.0 + 0.5 * 4999, 10)
    assert result.y_min.min() == pytest.approx(y.min())
    assert result.y_max.max() == pytest.approx(y.max())
    assert result.x[0] >= 2.0


def test_an_irregular_series_keeps_its_x(tmp_path: Path) -> None:
    x = np.cumsum(np.random.default_rng(0).uniform(0.1, 1.0, 3000))
    y = np.cos(x)
    spec = write_series(tmp_path / "s.h5", y, x)

    assert spec.irregular_x
    with h5py.File(spec.hdf5_path) as handle:
        assert np.array_equal(handle[spec.x_dataset][:], x)
        assert np.array_equal(handle[spec.y_dataset][:], y)


def test_an_unsorted_x_is_refused_where_it_is_written(tmp_path: Path) -> None:
    with pytest.raises(NonMonotonicXError, match="sample 2"):
        write_series(tmp_path / "s.h5", [1.0, 2.0, 3.0], [0.0, 2.0, 1.0])


def test_mismatched_lengths_are_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidSourceSpecError, match="shape"):
        write_series(tmp_path / "s.h5", [1.0, 2.0, 3.0], [0.0, 1.0])
