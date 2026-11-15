"""What to draw for a series, for any plotting library.

`query_range` answers "what is in this x range, at about this many
buckets". Drawing it well takes a few decisions more, the same whatever
draws it: how many buckets a view of a given pixel width needs, when the
view has not changed and need not be drawn again, when to stop drawing an
envelope and draw the raw line, and where to mark missing samples. This
module makes those decisions and hands back plain numpy arrays, so a plot
in matplotlib (`lightspeed.mpl`), Qt, a browser or anything else draws the
same picture from the same `Frame`.

A `SeriesView` follows one series as its view changes::

    view = SeriesView(handle, spec)
    x0, x1 = view.full_x_range()
    frame = view.frame(x0, x1, width_px=800)
    # draw frame.x / frame.y_min / frame.y_max as a band (frame.envelope) or
    # a line, frame.marks as points, frame.rug as ticks along the x axis
    ...
    frame = view.frame(new_x0, new_x1, width_px=800)  # None: nothing changed

Nothing here imports a plotting library.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .cache import CacheHandle, SourceSpec
from .query import QueryResult, full_x_range, query_range
from .status import NAN_KIND, UNKNOWN_KIND, kinds_in_mask
from .timing import TimingProbeLike

# Buckets across the view when its pixel width is not known (a figure that
# has not been laid out yet); once it is, one bucket per pixel column.
DEFAULT_TARGET_BUCKETS = 2000

# How a missing sample is pointed out once the view is zoomed to raw
# samples: a mark at the sample's x, at the height of the last good sample
# before it, so a single bad reading is seen rather than just leaving a hole
# in the line. Zoomed out, a bucket with missing samples draws its good ones,
# and a tick along the foot of the view says it holds missing ones.
MARKER_SHAPES = ("cross", "circle", "square", "triangle", "diamond", "none")
# Whether missing samples are marked at all.
MISSING_MARKERS = ("cross", "none")
DEFAULT_MISSING_MARKER = "cross"
MISSING_MARK_COLOR = "#d62728"


@dataclass(frozen=True)
class MissingStyle:
    """How one kind of missing sample is shown: its marker shape (one of
    `MARKER_SHAPES`), its colour, and its name in a legend (None: no entry)."""

    label: str | None = None
    marker: str = "cross"
    color: str = MISSING_MARK_COLOR


# The two kinds every series can have. A plain NaN is a red cross, unnamed;
# a status code no one declared is grey.
DEFAULT_MISSING_STYLES: dict[int, MissingStyle] = {
    NAN_KIND: MissingStyle(),
    UNKNOWN_KIND: MissingStyle(label="Unknown status", color="#7f7f7f"),
}


def missing_styles(styles: dict[int, MissingStyle] | None = None) -> dict[int, MissingStyle]:
    """`DEFAULT_MISSING_STYLES` with `styles` over them."""
    return {**DEFAULT_MISSING_STYLES, **(styles or {})}


def missing_sample_marks(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Where to draw the marks for the NaNs in `y`: their x, at the last good y.

    A missing sample before any good one takes the first good value after it
    instead; with no good samples at all there is nothing to place them on.
    """
    y = np.asarray(y, dtype=np.float64)
    return missing_kind_marks(x, y, np.isnan(y))


def missing_kind_marks(x: np.ndarray, y: np.ndarray, is_kind: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """As `missing_sample_marks`, for the samples `is_kind` picks out (which are NaN in `y`)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    is_kind = np.asarray(is_kind, dtype=bool)
    missing = np.isnan(y)
    if not is_kind.any() or missing.all():
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)
    good = np.flatnonzero(~missing)
    # Index of the last good sample at or before each position; positions
    # before the first good sample get the first good one.
    last_good = good[np.clip(np.searchsorted(good, np.arange(len(y)), side="right") - 1, 0, None)]
    return x[is_kind], y[last_good[is_kind]]


def kinds_present(result: QueryResult) -> list[int]:
    """Every kind of missing in a query's points: for a query over a whole series, the series'."""
    if result.missing is None or not len(result.missing):
        return []
    return kinds_in_mask(int(np.bitwise_or.reduce(result.missing)))


def indicator_label(result: QueryResult) -> str:
    """Short description of what the view shows: raw samples or an envelope."""
    if result.raw:
        return f"raw · {result.sample_count:,} samples"
    points = int(result.x.shape[0])
    per_bucket = result.sample_count / points if points else 0.0
    return f"min/max · ~{per_bucket:,.0f} samples/bucket"


@dataclass(frozen=True)
class Frame:
    """Everything to draw for one view of a series.

    - `x`, `y_min`, `y_max`: the points. Draw a band between `y_min` and
      `y_max` with edges along both when `envelope` is true; when it is false
      every point is a raw sample (`y_min == y_max`), so draw one line
      through `y_min`. A NaN is a gap in either.
    - `marks`: zoomed in to raw samples, for each kind of missing sample
      present, the (x, y) to put that kind's marker at.
    - `rug`: zoomed out, for each kind present, the x of every bucket that
      holds that kind of missing sample - ticks along the foot of the view.
    - `label`: what the view shows, for a corner badge.

    `marks` and `rug` are keyed by kind (`lightspeed.status`); a kind not in
    them has nothing to draw in this frame. `result` is the query the frame
    was made from.
    """

    result: QueryResult
    marks: dict[int, tuple[np.ndarray, np.ndarray]]
    rug: dict[int, np.ndarray]
    label: str

    @property
    def x(self) -> np.ndarray:
        return self.result.x

    @property
    def y_min(self) -> np.ndarray:
        return self.result.y_min

    @property
    def y_max(self) -> np.ndarray:
        return self.result.y_max

    @property
    def envelope(self) -> bool:
        return not self.result.raw

    @classmethod
    def of(cls, result: QueryResult) -> "Frame":
        marks: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        rug: dict[int, np.ndarray] = {}
        if result.missing is not None and len(result.x):
            for kind in kinds_present(result):
                has_kind = (result.missing >> kind & 1).astype(bool)
                if result.raw:
                    marks[kind] = missing_kind_marks(result.x, result.y_min, has_kind)
                else:
                    rug[kind] = np.asarray(result.x[has_kind], dtype=np.float64)
        return cls(result=result, marks=marks, rug=rug, label=indicator_label(result))


@dataclass
class SeriesView:
    """One series, followed through the views a plot shows of it.

    Call `frame` whenever the plot's x range or width changes; it returns
    what to draw, or None when that is what was drawn last.
    """

    handle: CacheHandle
    spec: SourceSpec
    # A cap on the buckets across the view, for a series that need not be
    # drawn at pixel resolution; None draws one bucket per pixel column.
    target_buckets: int | None = None
    timing: TimingProbeLike | None = None

    # The (x_start, x_end, buckets) of the last frame, so asking again for
    # what is already drawn costs nothing.
    _drawn: tuple[float, float, int] | None = field(default=None, init=False, repr=False)

    def full_x_range(self) -> tuple[float, float]:
        """The series' whole x extent, on the axis (after `x0`/`dx`)."""
        return full_x_range(self.handle, self.spec)

    def buckets_for(self, width_px: float | None) -> int:
        """How many buckets a view `width_px` pixels wide needs: one per pixel
        column, `DEFAULT_TARGET_BUCKETS` when the width is not known, and no
        more than `target_buckets`."""
        buckets = max(1, int(width_px)) if width_px and width_px > 1 else DEFAULT_TARGET_BUCKETS
        if self.target_buckets is not None:
            buckets = min(buckets, max(1, self.target_buckets))
        return buckets

    def frame(self, x_start: float, x_end: float, width_px: float | None = None, *, force: bool = False) -> Frame | None:
        """What to draw for x from `x_start` to `x_end` across `width_px`
        pixels; None if that is the view the last frame was for (unless
        `force`)."""
        buckets = self.buckets_for(width_px)
        drawn = (x_start, x_end, buckets)
        if not force and self._drawn == drawn:
            return None
        result = query_range(self.handle, self.spec, x_start, x_end, buckets, timing=self.timing)
        self._drawn = drawn
        return Frame.of(result)
