# types.py

from typing import NewType

# type aliases
Role = NewType("Role", str)
Name = NewType("Name", str)

# constants (global assignments)
ADMIN_ROLE = Role("admin")
USER_ROLE = Role("user")

class Greeter:
    """Interface‐style base class for greeting behavior."""
    def greet(self) -> str:
        raise NotImplementedError

# simple global assignment
DEFAULT_ROLE = USER_ROLE

def type_func() -> str:
    # final link in our 4-step chain
    return "chain complete"
