#!/bin/sh
# Checks the Haskell package is ready to release from HEAD: the tree is clean,
# HEAD has a haskell-v* tag, and that tag matches `version:` in
# lightspeed.cabal. Run it before `cabal sdist`; it exits non-zero on any
# mismatch.
#
#   ./check-release.sh                  # the haskell-v* tag on HEAD
#   ./check-release.sh haskell-v0.0.2   # a tag you are about to make
set -eu
cd "$(dirname "$0")"

cabal_version=$(sed -n 's/^version:[[:space:]]*\([^[:space:]]*\).*/\1/p' lightspeed.cabal)
if [ -z "$cabal_version" ]; then
    echo "error: no version: line in lightspeed.cabal" >&2
    exit 1
fi

if [ $# -ge 1 ]; then
    tag=$1
else
    tag=$(git tag --points-at HEAD --list 'haskell-v*')
    case $tag in
        "") echo "error: HEAD has no haskell-v* tag (lightspeed.cabal says $cabal_version; tag it haskell-v$cabal_version)" >&2; exit 1 ;;
        *"
"*) echo "error: HEAD has more than one haskell-v* tag:" $tag >&2; exit 1 ;;
    esac
fi

if [ "$tag" != "haskell-v$cabal_version" ]; then
    echo "error: tag $tag does not match lightspeed.cabal version $cabal_version (expected haskell-v$cabal_version)" >&2
    exit 1
fi

if [ -n "$(git status --porcelain -- .)" ]; then
    echo "error: uncommitted changes under haskell/; commit them before releasing" >&2
    exit 1
fi

echo "ok: $tag matches lightspeed.cabal"
