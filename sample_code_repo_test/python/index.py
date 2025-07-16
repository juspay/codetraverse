# index.py

from typing import List
from models import Person
from utils import greet_user, util_func
from types import Role, Greeter, ADMIN_ROLE, USER_ROLE, DEFAULT_ROLE

# Top‐level variable (should be picked up as kind="variable")
APP_NAME = "PyTraverse"

def main() -> None:
    print("Starting application:", APP_NAME)

    # integer & string literals, typed constructor call
    user = Person(1, "Alice", ADMIN_ROLE)
    print("User greeting:", greet_user(user))

    # annotated variable and loop
    roles: List[Role] = [ADMIN_ROLE, USER_ROLE]
    for r in roles:
        print("Role value:", r)

    # interface‐typed variable
    greeter: Greeter = Person(2, "Bob", USER_ROLE)
    print("Greeter says:", greeter.greet())

    # ── Chain entry point (step 1 → 2)
    func_main()

def func_main() -> None:
    util_func()

if __name__ == "__main__":
    main()
