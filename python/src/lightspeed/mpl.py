"""Drawing a series with matplotlib: `ZoomSync`, `plot_envelope` and friends.

Needs matplotlib (`pip install "lightspeed-series[mpl]"`). Everything here
draws a `lightspeed.view.Frame`; what to draw is decided there, so another
plotting library can draw the same picture without this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.text import Text

from .cache import CacheHandle, SourceSpec, build_or_get_cache
from .constants import DEFAULT_CHUNK_SIZE, PLOT_SERIES_HOOK
from .query import QueryResult
from .timing import TimingProbeLike
from .view import (
    DEFAULT_MISSING_MARKER,
    DEFAULT_MISSING_STYLES,
    DEFAULT_TARGET_BUCKETS,
    MISSING_MARK_COLOR,
    MISSING_MARKERS,
    Frame,
    MissingStyle,
    SeriesView,
    indicator_label,
    kinds_present,
    missing_kind_marks,
    missing_sample_marks,
    missing_styles,
)

# The names from lightspeed.view are re-exported: they were defined here
# before that module held them.
__all__ = [
    "DEFAULT_MISSING_MARKER",
    "DEFAULT_MISSING_STYLES",
    "DEFAULT_TARGET_BUCKETS",
    "INDICATOR_GID",
    "MARK_SHAPES",
    "MISSING_GID",
    "MISSING_MARKERS",
    "MISSING_MARK_COLOR",
    "MissingMarks",
    "MissingStyle",
    "ZoomSync",
    "add_indicator",
    "add_missing_marks",
    "indicator_label",
    "kinds_present",
    "missing_kind_marks",
    "missing_sample_marks",
    "plot_envelope",
    "plot_series",
    "series_x_union",
    "update_envelope_artists",
]

INDICATOR_GID = "lightspeed-envelope-indicator"
MISSING_GID = "lightspeed-missing"
DEFAULT_FILL_ALPHA = 1.0
MISSING_MARK_SIZE_PT = 5.0

# lightspeed.view's marker shapes, as matplotlib markers.
MARK_SHAPES = {"cross": "x", "circle": "o", "square": "s", "triangle": "^", "diamond": "D", "none": None}
# Zoomed out, a bucket holding a kind of missing sample gets a tick of that
# kind's colour along the foot of the axes, this far up (axes fraction).
RUG_Y = 0.0
RUG_MARKER_SIZE_PT = 6.0

_EMPTY = np.array([], dtype=np.float64)


class MissingMarks:
    """The marks for a series' missing samples, one pair of lines per kind of missing.

    Draws a frame's `marks` (zoomed in: each missing sample at the height of
    the last good one) and its `rug` (zoomed out: a tick along the foot of
    the axes for each bucket holding that kind).

    Lines are made for the kinds `kinds_present` names (a series' whole
    extent, which the first, zoomed-out query shows), so the legend - built
    once the figure is drawn - names every kind the series has.
    """

    def __init__(
        self,
        ax: Axes,
        *,
        kinds_present: list[int],
        styles: dict[int, MissingStyle] | None = None,
        enabled: bool = True,
    ) -> None:
        self.ax = ax
        self.enabled = enabled
        all_styles = missing_styles(styles)
        self.points: dict[int, Line2D] = {}
        self.rugs: dict[int, Line2D] = {}
        if not enabled:
            return
        for kind in kinds_present:
            style = all_styles.get(kind, MissingStyle())
            shape = MARK_SHAPES.get(style.marker, "x")
            if shape is None:
                continue
            filled = shape != "x"
            (points,) = ax.plot(
                [], [],
                linestyle="none",
                marker=shape,
                markersize=MISSING_MARK_SIZE_PT,
                markeredgewidth=1.0,
                color=style.color,
                markerfacecolor=style.color if filled else "none",
                label=style.label or "_nolegend_",
                zorder=4,
                gid=MISSING_GID,
            )
            (rug,) = ax.plot(
                [], [],
                linestyle="none",
                marker="|",
                markersize=RUG_MARKER_SIZE_PT,
                markeredgewidth=1.0,
                color=style.color,
                transform=ax.get_xaxis_transform(),
                label="_nolegend_",
                zorder=4,
                clip_on=False,
            )
            # Marks sit inside the axes; they must not move its layout (and an
            # empty, unclipped line would give tight_layout nonsense bounds).
            points.set_in_layout(False)
            rug.set_in_layout(False)
            self.points[kind] = points
            self.rugs[kind] = rug

    def update(self, frame: Frame | QueryResult) -> None:
        if isinstance(frame, QueryResult):
            frame = Frame.of(frame)
        for kind in self.points:
            mx, my = frame.marks.get(kind, (_EMPTY, _EMPTY))
            self.points[kind].set_data(mx, my)
            rug_x = frame.rug.get(kind, _EMPTY)
            self.rugs[kind].set_data(rug_x, np.full(rug_x.shape, RUG_Y))
            # Both stay visible, holding no data when not in use: a hidden
            # line would also hide its symbol in the legend.

    def get_visible(self) -> bool:
        """Whether anything is marked now."""
        return any(len(line.get_xdata()) for line in [*self.points.values(), *self.rugs.values()])


def plot_envelope(
    ax: Axes,
    result: QueryResult | Frame,
    *,
    color: str | None = None,
    fill_color: str | None = None,
    fill_alpha: float | None = None,
    line_kwargs: dict | None = None,
    fill_kwargs: dict | None = None,
    missing_marker: str = DEFAULT_MISSING_MARKER,
    missing_styles: dict[int, MissingStyle] | None = None,
    label: str | None = None,
) -> tuple[Line2D, Line2D, PolyCollection, MissingMarks]:
    """Draws a min/max envelope: two edge lines and the band between them,
    plus the marks for missing samples (see `MissingMarks`).

    `color` is the edge colour and, unless `fill_color` is given, the band
    colour too; the band is opaque unless `fill_alpha` says otherwise. With no
    colour given at all the series takes one step of the axes' colour cycle,
    so all three artists read as a single series rather than one colour per line.
    `label` names the series in a legend: one entry, on the min line, which
    is the one shown at every zoom.
    """
    frame = result if isinstance(result, Frame) else Frame.of(result)
    line_kwargs = dict(line_kwargs or {})
    fill_kwargs = dict(fill_kwargs or {})
    if color is None:
        color = line_kwargs.get("color") or ax._get_lines.get_next_color()
    line_kwargs["color"] = color
    fill_kwargs["color"] = fill_color if fill_color is not None else color
    if fill_alpha is not None:
        fill_kwargs["alpha"] = fill_alpha

    line_kwargs.setdefault("linewidth", 0.8)
    fill_kwargs.setdefault("alpha", DEFAULT_FILL_ALPHA)
    fill_kwargs.setdefault("linewidth", 0.0)

    line_label = line_kwargs.pop("label", None) if label is None else label
    line_kwargs.pop("label", None)
    fill_kwargs.pop("label", None)
    (line_min,) = ax.plot(frame.x, frame.y_min, label="_nolegend_" if line_label is None else line_label, **line_kwargs)
    (line_max,) = ax.plot(frame.x, frame.y_max, label="_nolegend_", **line_kwargs)
    fill = ax.fill_between(frame.x, frame.y_min, frame.y_max, label="_nolegend_", **fill_kwargs)
    marks = MissingMarks(
        ax, kinds_present=kinds_present(frame.result), styles=missing_styles, enabled=missing_marker != "none"
    )
    _apply_envelope_mode(line_max, fill, marks, frame)

    return line_min, line_max, fill, marks


def add_missing_marks(ax: Axes, *, visible: bool = True) -> Line2D:
    """An (initially empty) marker-only line for missing-sample marks."""
    (marks,) = ax.plot(
        [], [],
        linestyle="none",
        marker="x",
        markersize=MISSING_MARK_SIZE_PT,
        markeredgewidth=1.0,
        color=MISSING_MARK_COLOR,
        label="_nolegend_",
        zorder=4,
    )
    marks.set_visible(visible)
    # Remembered here so the mode switch below can hide/show without losing it.
    marks._lightspeed_marks_enabled = visible  # type: ignore[attr-defined]
    return marks


def update_envelope_artists(
    line_min: Line2D,
    line_max: Line2D,
    fill: PolyCollection,
    result: QueryResult | Frame,
    marks: MissingMarks | None = None,
) -> None:
    frame = result if isinstance(result, Frame) else Frame.of(result)
    line_min.set_data(frame.x, frame.y_min)
    line_max.set_data(frame.x, frame.y_max)
    # fill is a FillBetweenPolyCollection; set_data() (not set_verts()) is required
    # so its cached _bbox used by get_datalim()/relim() is refreshed too.
    fill.set_data(frame.x, frame.y_min, frame.y_max)
    _apply_envelope_mode(line_max, fill, marks, frame)


def _apply_envelope_mode(line_max: Line2D, fill: PolyCollection, marks: MissingMarks | None, frame: Frame) -> None:
    """Show the envelope only when there is one.

    Once the frame is raw samples, y_min and y_max coincide, so the max line
    and the fill would just retrace the min line; hide them and let the min
    line stand as the plain data line.
    """
    line_max.set_visible(frame.envelope)
    fill.set_visible(frame.envelope)
    if marks is not None:
        marks.update(frame)


def add_indicator(ax: Axes, color: str, font: Any | None = None) -> Text:
    """Adds a small corner badge to the axes, stacked below any earlier badges.

    ``font`` is a matplotlib FontProperties; without one the badge is drawn
    at rcParams' "x-small".
    """
    existing = sum(1 for text in ax.texts if text.get_gid() == INDICATOR_GID)
    font_kwargs: dict[str, Any] = {"fontproperties": font} if font is not None else {"fontsize": "x-small"}
    return ax.text(
        0.99,
        0.98 - 0.08 * existing,
        "",
        transform=ax.transAxes,
        ha="right",
        va="top",
        color=color,
        **font_kwargs,
        gid=INDICATOR_GID,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": color, "alpha": 0.8},
        zorder=10,
    )


_SERIES_X_RANGE = "_lightspeed_series_x_range"


def series_x_union(ax: Axes, x_start: float, x_end: float) -> tuple[float, float]:
    """Record a series' x extent on `ax`, and return the extent of every series
    on `ax` and on the axes sharing its x: the range the axes should open on."""
    own = getattr(ax, _SERIES_X_RANGE, None)
    if own is not None:
        x_start, x_end = min(own[0], x_start), max(own[1], x_end)
    setattr(ax, _SERIES_X_RANGE, (x_start, x_end))
    for sibling in ax.get_shared_x_axes().get_siblings(ax):
        other = getattr(sibling, _SERIES_X_RANGE, None)
        if other is not None:
            x_start, x_end = min(other[0], x_start), max(other[1], x_end)
    return x_start, x_end


@dataclass
class ZoomSync:
    """Keeps a min/max envelope on an Axes in sync with the current xlim."""

    ax: Axes
    handle: CacheHandle
    spec: SourceSpec
    # A cap on the buckets across the axes, for a series that need not be
    # drawn at pixel resolution; None draws one bucket per pixel column.
    target_buckets: int | None = None
    on_query: Callable[[QueryResult], None] | None = None
    timing: TimingProbeLike | None = None
    # Edge colour (None: next in the axes' cycle), band colour (None: same as
    # the edges) and band opacity (None: opaque).
    color: str | None = None
    fill_color: str | None = None
    fill_alpha: float | None = None
    # Show a corner badge saying whether the axes currently shows raw samples
    # or a min/max envelope, so a viewer can tell how far they have zoomed in.
    indicator: bool = True
    # The badge's type, a matplotlib FontProperties; None is rcParams' "x-small".
    indicator_font: Any | None = None
    # "cross" marks each missing sample in the raw view; "none" leaves the gap.
    missing_marker: str = DEFAULT_MISSING_MARKER
    # How each kind of missing sample is marked, by kind (status.py); kinds
    # not named here take DEFAULT_MISSING_STYLES, else a red cross.
    missing_styles: dict[int, MissingStyle] | None = None
    # The series' name in a legend; None leaves it out.
    label: str | None = None

    _view: SeriesView = field(init=False, repr=False)
    _line_min: Line2D | None = field(default=None, init=False, repr=False)
    _line_max: Line2D | None = field(default=None, init=False, repr=False)
    _fill: PolyCollection | None = field(default=None, init=False, repr=False)
    _marks: MissingMarks | None = field(default=None, init=False, repr=False)
    _indicator: Text | None = field(default=None, init=False, repr=False)
    _cid: int | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if getattr(self.ax, PLOT_SERIES_HOOK, None) is not None:
            raise TypeError(
                f"{type(self.ax).__name__} draws large series itself: plot this one with "
                "lightspeed.mpl.plot_series(ax, spec, ...), which hands it over, rather than ZoomSync"
            )
        self._view = SeriesView(self.handle, self.spec, target_buckets=self.target_buckets, timing=self.timing)
        self._install_initial_artists()
        self._connect()

    def _install_initial_artists(self) -> None:
        # The axes open on every series they show - this one, and any already
        # on them or on axes sharing their x - not on this series alone:
        # several recordings, one source each, sit side by side on one axis.
        x_start, x_end = series_x_union(self.ax, *self._view.full_x_range())
        # Setting the limits notifies every series already on these axes, and
        # every panel sharing them, which redraw for the wider range. A series
        # told the range it is already drawn at does nothing (SeriesView.frame).
        self.ax.set_xlim(x_start, x_end)
        frame = self._view.frame(x_start, x_end, self._width_px(), force=True)
        assert frame is not None
        self._line_min, self._line_max, self._fill, self._marks = plot_envelope(
            self.ax, frame, color=self.color, fill_color=self.fill_color, fill_alpha=self.fill_alpha,
            missing_marker=self.missing_marker, missing_styles=self.missing_styles, label=self.label,
        )
        if self.indicator:
            self._indicator = add_indicator(self.ax, self._line_min.get_color(), self.indicator_font)
            self._indicator.set_text(frame.label)
        self.ax.relim()
        self.ax.autoscale_view(scalex=False, scaley=True)
        if self.on_query is not None:
            self.on_query(frame.result)

    def _connect(self) -> None:
        self._cid = self.ax.callbacks.connect("xlim_changed", self._on_xlim_changed)

    def _on_xlim_changed(self, ax: Axes) -> None:
        x_start, x_end = ax.get_xlim()
        redraw_start = self.timing.start() if self.timing is not None else None
        frame = self._view.frame(x_start, x_end, self._width_px())
        if frame is None:
            # Already showing exactly this. Another series installing itself
            # on these axes, or a panel sharing them, sets the limits we are
            # at; requerying would draw the same picture again.
            return

        update_envelope_artists(self._line_min, self._line_max, self._fill, frame, self._marks)
        if self._indicator is not None:
            self._indicator.set_text(frame.label)
        ax.relim()
        ax.autoscale_view(scalex=False, scaley=True)
        if self.on_query is not None:
            self.on_query(frame.result)
        ax.figure.canvas.draw_idle()
        if self.timing is not None and redraw_start is not None:
            self.timing.log(
                "lightspeed.zoomsync.redraw",
                redraw_start,
                (
                    ("x_start", x_start),
                    ("x_end", x_end),
                    ("level", frame.result.level),
                    ("points", int(frame.x.shape[0])),
                ),
            )

    def _width_px(self) -> float | None:
        try:
            return float(self.ax.get_window_extent().width)
        except Exception:
            return None

    def _estimate_target_buckets(self) -> int:
        return self._view.buckets_for(self._width_px())

    @property
    def lines(self) -> tuple[Line2D, Line2D]:
        """The envelope's (min, max) edge lines. Zoomed in to raw samples,
        the min line is the data line and the max line is hidden."""
        assert self._line_min is not None and self._line_max is not None
        return self._line_min, self._line_max

    @property
    def fill(self) -> PolyCollection:
        """The band between the edge lines (hidden when zoomed to raw samples)."""
        assert self._fill is not None
        return self._fill

    def disconnect(self) -> None:
        if self._cid is not None:
            self.ax.callbacks.disconnect(self._cid)
            self._cid = None


def plot_series(
    ax: Any,
    spec: SourceSpec,
    *,
    label: str | None = None,
    color: str | None = None,
    fill_color: str | None = None,
    fill_alpha: float | None = None,
    target_buckets: int | None = None,
    missing_marker: str = DEFAULT_MISSING_MARKER,
    missing_styles: dict[int, MissingStyle] | None = None,
    indicator: bool = True,
    indicator_font: Any | None = None,
    cache_dir: Any = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    timing: TimingProbeLike | None = None,
    progress: Callable[[int, int], None] | None = None,
    on_query: Callable[[QueryResult], None] | None = None,
) -> Any:
    """Plots the series `spec` reads on `ax`, kept in step with its zoom: the
    one call from a source to a zoomable envelope.

    Builds the series' cache if there is none yet (`cache_dir`, `chunk_size`,
    `progress` as `build_or_get_cache` takes them) and returns the
    `ZoomSync` drawing it; the other arguments are `ZoomSync`'s.

    An `ax` that defines `__lightspeed_plot_series__` (the name is
    `lightspeed.constants.PLOT_SERIES_HOOK`) draws the series itself: it is
    called with `spec` and every keyword argument above, and what it
    returns is returned. That lets an Axes-like object - one recording what
    is drawn on it, say - take in a script that only ever calls
    `plot_series`, without lightspeed knowing about it.
    """

    options = dict(
        label=label, color=color, fill_color=fill_color, fill_alpha=fill_alpha, target_buckets=target_buckets,
        missing_marker=missing_marker, missing_styles=missing_styles, indicator=indicator,
        indicator_font=indicator_font, cache_dir=cache_dir, chunk_size=chunk_size, timing=timing,
        progress=progress, on_query=on_query,
    )
    hook = getattr(ax, PLOT_SERIES_HOOK, None)
    if hook is not None:
        return hook(spec, **options)
    handle = build_or_get_cache(spec, cache_dir=cache_dir, chunk_size=chunk_size, timing=timing, progress=progress)
    return ZoomSync(
        ax, handle, spec, target_buckets=target_buckets, on_query=on_query, timing=timing, color=color,
        fill_color=fill_color, fill_alpha=fill_alpha, indicator=indicator, indicator_font=indicator_font,
        missing_marker=missing_marker, missing_styles=missing_styles, label=label,
    )
