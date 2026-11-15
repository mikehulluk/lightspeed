-- | Fast, zoomable plots of very large series.
--
-- The Haskell implementation of lightspeed. Nothing is implemented yet; it
-- will share the cache file format with the Python package in @python/@.
module Lightspeed
  ( version
  ) where

import Data.Version (showVersion)
import qualified Paths_lightspeed

-- | The package version, from @lightspeed.cabal@. Independent of the Python
-- package's version; the two agree on the cache's schema version.
version :: String
version = showVersion Paths_lightspeed.version
