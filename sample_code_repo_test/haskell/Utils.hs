{-# LANGUAGE DeriveFunctor #-}

module Utils
   ( MyClass(..)
   , Greeter(..)
   , defaultMethod
   , newMethod
   , capitalizeWords
   ) where

import Data.Char (toUpper)

-- | A little alias for a list
type AliasList a = [a]

-- | A newtype with a derived Functor instance
newtype NT a = NT a deriving Functor

-- | A closed type family
type family F a
type instance F Int = String

-- | A record‐style data type
data MyClass = MyClass { unMyClass :: Int } deriving (Eq, Show)

-- | A pattern synonym
pattern SimpleUser name <- MyClass name

-- | A type class with a default method
class Greeter a where
  greet :: a -> String
  default greet :: Show a => a -> String
  greet x = "Hello " ++ show x

-- | Rely on the default 'greet' for MyClass
instance Greeter MyClass where

-- | A little I/O action
defaultMethod :: IO ()
defaultMethod = putStrLn "defaultMethod in Utils"

-- | A function with a 'let' binding
newMethod :: Int -> Int
newMethod x = let y = x + 1 in y

-- | A helper with a where‐clause
capitalizeWords :: String -> String
capitalizeWords s = unwords (map cap (words s))
  where
    cap (c:cs) = toUpper c : cs
    cap []     = []
