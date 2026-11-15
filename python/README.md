# lightspeed

Fast, zoomable plots of very large series.

A series of tens of millions of samples is too long to draw point by point.
lightspeed reads it once, in chunks, and reduces it into a pyramid of min/max
levels of detail, which it caches in an HDF5 file. A plot then asks for the
x range in view at the resolution the axes can show, and gets back a
min/max envelope of a few thousand buckets whatever the zoom - and the raw
samples once you zoom in far enough. Spikes are never averaged away.

The cache is keyed by a hash of the source's contents, so a second open of the
same data is immediate, and several processes can share one cache directory.

## Install

```sh
pip install "lightspeed-series[mpl]"   # with matplotlib plotting
pip install lightspeed-series          # the core only: numpy and h5py
```

The PyPI name is `lightspeed-series`; the import name is `lightspeed`.

## The parts

| Module | Needs | What it does |
|---|---|---|
| `lightspeed` (`cache`, `query`) | numpy, h5py | Builds and opens caches; `query_range` returns the buckets (or raw samples) for an x range |
| `lightspeed.view` | numpy, h5py | What to draw: `SeriesView` follows a series through pans and zooms and returns a `Frame` for each view |
| `lightspeed.mpl` | matplotlib (`[mpl]`) | Draws frames with matplotlib: `ZoomSync`, `plot_envelope` |

`import lightspeed` does not import matplotlib. `lightspeed.ZoomSync` (and
`plot_envelope`, `update_envelope_artists`) can still be named from there,
and load `lightspeed.mpl` when first used.

## With matplotlib

```python
import matplotlib.pyplot as plt
from lightspeed import SourceSpec, ZoomSync, build_or_get_cache, close_cache

# A 1-D dataset in an HDF5 file, sampled at x = 0, 1, 2, ...
spec = SourceSpec.uniform("signal.h5", "/y", x0=0.0, dx=1.0)
handle = build_or_get_cache(spec)

fig, ax = plt.subplots()
sync = ZoomSync(ax=ax, handle=handle, spec=spec)  # re-queries on pan and zoom
plt.show()

sync.disconnect()
close_cache(handle)
```

`examples/demo.py` builds a 20-million-sample source and zooms into it.

## With anything else

`lightspeed.view` makes the decisions a plot of a large series needs, so
another plotting tool has only to draw what it is given:

```python
from lightspeed import SeriesView, SourceSpec, build_or_get_cache

spec = SourceSpec.uniform("signal.h5", "/y", x0=0.0, dx=1.0)
view = SeriesView(build_or_get_cache(spec), spec)

frame = view.frame(x_start, x_end, width_px=800)  # call again on every pan/zoom
if frame is not None:  # None: the view has not changed since the last frame
    if frame.envelope:
        ...  # a band from frame.y_min to frame.y_max along frame.x
    else:
        ...  # zoomed in to raw samples: one line through frame.y_min
    for kind, (mx, my) in frame.marks.items():
        ...  # zoomed in: a marker at each missing sample
    for kind, rug_x in frame.rug.items():
        ...  # zoomed out: a tick for each bucket holding missing samples
    frame.label  # "min/max · ~4,096 samples/bucket", for a corner badge
```

A frame holds numpy arrays and nothing else: NaN in `y_min`/`y_max` is a gap.
`kind` names the kind of missing sample (a NaN, an unknown status code, or a
declared one), and `lightspeed.view.MissingStyle` and `DEFAULT_MISSING_STYLES`
give each a marker shape and colour, so every tool can mark them alike.

`examples/svg_without_matplotlib.py` draws a five-million-sample series as an
SVG file this way, with no plotting library at all.

## Cache directory

`build_or_get_cache(spec, cache_dir=...)` uses `cache_dir` if given; otherwise
`$LIGHTSPEED_CACHE_DIR`, then `%LOCALAPPDATA%\Lightspeed\Cache` on Windows,
`$XDG_CACHE_HOME/lightspeed`, or `~/.cache/lightspeed`.

## Licence

MIT.
