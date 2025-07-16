module Types
  ( func3
  , typeAlias
  , helper
  ) where

import Utils (MyClass(..), newMethod)

-- | A simple type synonym
type typeAlias = F Int

-- | A function with a `where` clause
helper :: Int -> Int
helper x = y
  where
    y = x * 2

-- | Calls into Utils.newMethod
func3 :: IO ()
func3 = do
  putStrLn "In Types.func3"
  let obj = MyClass 42
  print (newMethod (unMyClass obj))
  print (helper (unMyClass obj))
