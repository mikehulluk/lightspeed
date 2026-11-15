"""lightspeed.view: what to draw, without a plotting library."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import h5py
import numpy as np

from lightspeed import Frame, SeriesView, StatusMap
from lightspeed.cache import SourceSpec, build_or_get_cache, close_cache
from lightspeed.status import FIRST_DECLARED_KIND, NAN_KIND
from lightspeed.view import DEFAULT_TARGET_BUCKETS, missing_sample_marks


def _uniform(tmp_path: Path, values: np.ndarray, chunk_size: int = 8, status: np.ndarray | None = None):
    source = tmp_path / "source.h5"
    with h5py.File(source, "w") as handle:
        handle.create_dataset("/y", data=values)
        if status is not None:
            handle.create_dataset("/status", data=status)
    spec = SourceSpec.uniform(source, "/y", x0=0.0, dx=1.0)
    if status is not None:
        spec = spec.with_status("/status", StatusMap.from_meanings([(0, "valid"), (1, "skip"), (2, "absent")]))
    return spec, build_or_get_cache(spec, cache_dir=tmp_path / "cache", chunk_size=chunk_size)


def test_zoomed_out_is_an_envelope_and_zoomed_in_is_the_raw_line(tmp_path: Path) -> None:
    spec, handle = _uniform(tmp_path, np.sin(np.linspace(0, 20, 4096)))
    try:
        view = SeriesView(handle, spec)
        out = view.frame(*view.full_x_range(), width_px=50)
        assert out is not None and out.envelope and out.label.startswith("min/max")
        assert len(out.x) <= 2 * 50
        assert np.all(out.y_min <= out.y_max)

        near = view.frame(100, 120, width_px=50)
        assert near is not None and not near.envelope and near.label.startswith("raw")
        np.testing.assert_array_equal(near.y_min, near.y_max)
    finally:
        close_cache(handle)


def test_asking_again_for_the_same_view_returns_none(tmp_path: Path) -> None:
    spec, handle = _uniform(tmp_path, np.arange(1000.0))
    try:
        view = SeriesView(handle, spec)
        assert view.frame(0, 500, width_px=100) is not None
        assert view.frame(0, 500, width_px=100) is None
        assert view.frame(0, 500, width_px=100, force=True) is not None
        # A new width is a new view.
        assert view.frame(0, 500, width_px=200) is not None
    finally:
        close_cache(handle)


def test_buckets_follow_the_width_up_to_the_cap(tmp_path: Path) -> None:
    spec, handle = _uniform(tmp_path, np.arange(100.0))
    try:
        assert SeriesView(handle, spec).buckets_for(640.7) == 640
        assert SeriesView(handle, spec).buckets_for(None) == DEFAULT_TARGET_BUCKETS
        assert SeriesView(handle, spec).buckets_for(0) == DEFAULT_TARGET_BUCKETS
        assert SeriesView(handle, spec, target_buckets=50).buckets_for(640) == 50
    finally:
        close_cache(handle)


def test_missing_samples_are_marks_zoomed_in_and_rug_zoomed_out(tmp_path: Path) -> None:
    values = np.arange(4096.0)
    values[1000] = np.nan
    status = np.zeros(4096, dtype=np.uint8)
    status[3000] = 2  # absent: the first declared missing kind
    spec, handle = _uniform(tmp_path, values, status=status)
    try:
        view = SeriesView(handle, spec)
        out = view.frame(*view.full_x_range(), width_px=64)
        assert out is not None and out.envelope
        assert out.marks == {}
        assert set(out.rug) == {NAN_KIND, FIRST_DECLARED_KIND}
        (nan_x,) = out.rug[NAN_KIND]
        assert abs(nan_x - 1000) < 4096 / 32

        near = view.frame(990, 1010, width_px=64)
        assert near is not None and not near.envelope and near.rug == {}
        mx, my = near.marks[NAN_KIND]
        # At the missing sample's x, at the height of the last good one.
        np.testing.assert_array_equal(mx, [1000.0])
        np.testing.assert_array_equal(my, [999.0])
    finally:
        close_cache(handle)


def test_frame_of_a_result_matches_the_view(tmp_path: Path) -> None:
    from lightspeed import query_range

    spec, handle = _uniform(tmp_path, np.cos(np.linspace(0, 9, 2048)))
    try:
        frame = Frame.of(query_range(handle, spec, 0, 2047, 40))
        viewed = SeriesView(handle, spec).frame(0, 2047, width_px=40)
        assert viewed is not None
        np.testing.assert_array_equal(frame.x, viewed.x)
        np.testing.assert_array_equal(frame.y_max, viewed.y_max)
    finally:
        close_cache(handle)


def test_missing_sample_marks_before_the_first_good_sample() -> None:
    mx, my = missing_sample_marks(np.arange(4.0), np.array([np.nan, 5.0, np.nan, 7.0]))
    np.testing.assert_array_equal(mx, [0.0, 2.0])
    np.testing.assert_array_equal(my, [5.0, 5.0])


_BLOCK_MATPLOTLIB = """
import sys
class _Block:
    def find_spec(self, name, path=None, target=None):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
sys.meta_path.insert(0, _Block())
"""


def _run_without_matplotlib(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _BLOCK_MATPLOTLIB + textwrap.dedent(code)],
        capture_output=True,
        text=True,
    )


def test_the_core_needs_no_matplotlib(tmp_path: Path) -> None:
    result = _run_without_matplotlib(
        f"""
        import sys, h5py, numpy as np
        import lightspeed
        from lightspeed import SeriesView, SourceSpec, build_or_get_cache, close_cache
        with h5py.File({str(tmp_path / "s.h5")!r}, "w") as f:
            f["y"] = np.arange(10000.0)
        spec = SourceSpec.uniform({str(tmp_path / "s.h5")!r}, "/y", x0=0.0, dx=1.0)
        handle = build_or_get_cache(spec, cache_dir={str(tmp_path / "cache")!r})
        frame = SeriesView(handle, spec).frame(0, 9999, width_px=100)
        close_cache(handle)
        assert frame is not None and len(frame.x) > 0
        assert not any(m == "matplotlib" or m.startswith("matplotlib.") for m in sys.modules)
        print("ok")
        """
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_zoomsync_without_matplotlib_says_what_to_install() -> None:
    result = _run_without_matplotlib(
        """
        import lightspeed
        try:
            lightspeed.ZoomSync
        except ImportError as error:
            print(error)
        """
    )
    assert result.returncode == 0, result.stderr
    assert 'pip install "lightspeed-series[mpl]"' in result.stdout
