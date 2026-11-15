"""Draw a large series as SVG, with no plotting library: lightspeed.view only.

The same few lines are what any other tool - Qt, a browser canvas, a
terminal - needs: ask a SeriesView for a Frame at the view's x range and
pixel width, and draw its band (or line) and its missing-sample marks.

    python examples/svg_without_matplotlib.py   # writes _build/series.svg
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from lightspeed import SeriesView, SourceSpec, build_or_get_cache, close_cache

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "_build" / "svg-source.h5"
WIDTH, HEIGHT = 800, 240


def make_source() -> None:
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    x = np.arange(5_000_000, dtype=np.float64)
    y = np.sin(x * 2e-6) + 0.2 * np.random.default_rng(0).standard_normal(x.size)
    y[2_500_000] = np.nan  # one missing sample, shown by the rug
    with h5py.File(SOURCE, "w") as handle:
        handle.create_dataset("/y", data=y)


def to_svg(frame, x_start: float, x_end: float) -> str:
    lo = float(np.nanmin(frame.y_min))
    hi = float(np.nanmax(frame.y_max))

    def px(x):
        return (np.asarray(x) - x_start) / (x_end - x_start) * WIDTH

    def py(y):
        return HEIGHT - (np.asarray(y) - lo) / (hi - lo) * HEIGHT

    def points(xs, ys):
        return " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(xs, ys) if np.isfinite(b))

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">']
    if frame.envelope:
        # The band: along y_max, then back along y_min.
        band = points(np.r_[px(frame.x), px(frame.x)[::-1]], np.r_[py(frame.y_max), py(frame.y_min)[::-1]])
        parts.append(f'<polygon points="{band}" fill="#1f77b4"/>')
    else:
        parts.append(f'<polyline points="{points(px(frame.x), py(frame.y_min))}" fill="none" stroke="#1f77b4"/>')
    for mx, my in frame.marks.values():
        parts += [f'<text x="{a:.1f}" y="{b:.1f}" fill="#d62728">×</text>' for a, b in zip(px(mx), py(my))]
    for rug_x in frame.rug.values():
        parts += [f'<line x1="{a:.1f}" x2="{a:.1f}" y1="{HEIGHT}" y2="{HEIGHT - 8}" stroke="#d62728"/>' for a in px(rug_x)]
    parts.append(f'<text x="{WIDTH - 8}" y="16" text-anchor="end" font-size="12">{frame.label}</text></svg>')
    return "\n".join(parts)


def main() -> None:
    if not SOURCE.exists():
        make_source()
    spec = SourceSpec.uniform(SOURCE, "/y", x0=0.0, dx=1.0)
    handle = build_or_get_cache(spec, cache_dir=ROOT / "_build" / "cache")
    try:
        view = SeriesView(handle, spec)
        x_start, x_end = view.full_x_range()
        frame = view.frame(x_start, x_end, width_px=WIDTH)
        out = ROOT / "_build" / "series.svg"
        out.write_text(to_svg(frame, x_start, x_end), encoding="utf-8")
        print(f"{len(frame.x)} points ({frame.label}) -> {out}")
    finally:
        close_cache(handle)


if __name__ == "__main__":
    main()
