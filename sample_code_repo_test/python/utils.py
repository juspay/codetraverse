# utils.py

from models import Person, print_person, model_func

def greet_user(p: Person) -> str:
    # method call on instance, free‐function call
    print_person(p)
    return f"Welcome, {p.greet()}"

def util_func() -> None:
    # step 2 → 3 of the cross‐file chain
    model_func()
