module Main (main) where

import Lightspeed (version)
import System.Exit (exitFailure)

main :: IO ()
main
  | null version = exitFailure
  | otherwise = putStrLn ("lightspeed " ++ version)
