# models.py

from types import Role, Greeter, type_func

class Person(Greeter):
    """Represents a user in the system."""
    # class‐level assignment (should be picked up as class variable)
    count = 0

    def __init__(self, id: int, name: str, role: Role) -> None:
        self.id = id
        self.name = name
        self.role = role

    def greet(self) -> str:
        return f"Hello, {self.name}!"

    def set_name(self, name: str) -> None:
        self.name = name

def print_person(p: Person) -> None:
    print("Person details:", p.id, p.name, p.role)

def model_func() -> None:
    # step 3 → 4 of the cross-file chain
    type_func()
