# lightspeed

Fast, zoomable plots of very large series, from min/max level-of-detail
pyramids cached in HDF5.

This repository holds two implementations of the same library:

| Directory | Language | Package |
|---|---|---|
| [`python/`](python/) | Python | `lightspeed` on PyPI |
| [`haskell/`](haskell/) | Haskell | `lightspeed` (cabal) - not yet implemented |

Both read and write the same HDF5 cache file format: a cache built by one is
read by the other. The format is the contract between them, so a change to
it is made in both implementations, and its `schema_version` bumped, together.

## Planned

- **Rolling series**: live data arriving while the series is plotted, with the
  pyramid extended as samples come in rather than rebuilt.

## Python

```sh
cd python
uv sync
uv run pytest
uv build          # sdist and wheel into python/dist/
```

## Haskell

```sh
cd haskell
cabal build
cabal test
```

## Versions and releases

The two packages are released independently, each from its own git tags, so a
bug fix to one does not need a release of the other:

| Package | Tag | Version comes from |
|---|---|---|
| Python | `python-v0.0.4` | the tag (setuptools-scm; other tags are ignored) |
| Haskell | `haskell-v0.0.2` | `version:` in `haskell/lightspeed.cabal`; `haskell/check-release.sh` checks it matches the tag |

What makes the two work together is the cache file's `schema_version`, not the
package versions: any pair that agree on it can share a cache. A release that
changes the file format bumps `schema_version`, and both packages need a
release that reads it.

To release Python, push a tag; `.github/workflows/publish.yml` runs the tests,
builds, checks the built version matches the tag, and uploads to PyPI through
Trusted Publishing (no token):

```sh
git tag -a python-v0.0.4 -m "lightspeed (Python) 0.0.4"
git push origin python-v0.0.4
```

To release Haskell: set `version:` in `haskell/lightspeed.cabal`, commit, then

```sh
git tag haskell-v0.0.2
cd haskell
./check-release.sh     # fails unless the tag on HEAD matches lightspeed.cabal and the tree is clean
cabal sdist && cabal upload --publish dist-newstyle/sdist/lightspeed-0.0.2.tar.gz
```

## Licence

MIT - see [LICENSE](LICENSE).
