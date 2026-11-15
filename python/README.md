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
pip install lightspeed-series
```

The PyPI name is `lightspeed-series`; the import name is `lightspeed`.

## Use

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

## Cache directory

`build_or_get_cache(spec, cache_dir=...)` uses `cache_dir` if given; otherwise
`$LIGHTSPEED_CACHE_DIR`, then `%LOCALAPPDATA%\Lightspeed\Cache` on Windows,
`$XDG_CACHE_HOME/lightspeed`, or `~/.cache/lightspeed`.

## Licence

MIT.
