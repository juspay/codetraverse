module Main where

import Models    (func2)
import Types     (helper)
import Utils     (newMethod, defaultMethod, Greeter(..))

main :: IO ()
main = do
  -- step 1: call helper from Types
    let a = Types.helper 10
    let b = Utils.newMethod a
    let c = Utils.defaultMethod b
    Models.func2

  -- final: invoke the Greeter instance method
  putStrLn (greet (MyClass 42))
