module Models
  ( func2
  , User(..)
  ) where

import Types (func3)
import Utils (defaultMethod, Greeter(..))

-- | A record type for users
data User = User
  { userId   :: Int
  , userName :: String
  } deriving (Eq, Show)

-- | A custom instance overriding the default 'greet'
instance Greeter User where
  greet (User _ name) = "User says: " ++ name

-- | Chains into Types.func3 then Utils.defaultMethod
func2 :: IO ()
func2 = do
  putStrLn "In Models.func2"
  func3
  defaultMethod
