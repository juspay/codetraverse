# tests/adapters/test_python_adapter.py

import os
import json
import pytest
from codetraverse.adapters.python_adapter import adapt_python_components

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep", "python"))

@pytest.fixture(scope="module")
def adapted():
    raw = []
    for fname in ("index.json", "models.json", "types.json", "utils.json"):
        path = os.path.join(FDEP_DIR, fname)
        with open(path, encoding="utf-8") as f:
            raw.extend(json.load(f))
    # adapter returns {"nodes": [...], "edges": [...]}
    return adapt_python_components(raw, quiet=True)

def test_nodes_and_edges_structure(adapted):
    assert isinstance(adapted, dict)
    assert isinstance(adapted["nodes"], list)
    assert isinstance(adapted["edges"], list)

def test_core_nodes_present(adapted):
    ids = {n["id"] for n in adapted["nodes"]}
    # classes
    assert "Person" in ids
    assert "Greeter" in ids
    # free functions
    for fn in ("main", "func_main", "greet_user", "util_func",
               "print_person", "model_func", "type_func"):
        assert fn in ids, f"Expected function node {fn}"
    # methods
    for m in ("Person::__init__", "Person::greet",
              "Person::set_name", "Greeter::greet"):
        assert m in ids, f"Expected method node {m}"

def test_call_edges(adapted):
    calls = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "calls"
    }
    expected = {
        ("main",         "Person"),        # constructor
        ("main",         "func_main"),     
        ("main",         "greet_user"),
        ("main",         "greeter.greet"),
        ("main",         "print"),
        ("greet_user",   "p.greet"),
        ("greet_user",   "print_person"),
        ("util_func",    "model_func"),
        ("print_person", "print"),
        ("model_func",   "type_func"),
    }
    assert expected.issubset(calls)

def test_defines_edges(adapted):
    defs = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "defines"
    }
    expected = {
        ("Person::__init__",     "Person::__init__::self"),
        ("Person::greet",        "Person::greet::self"),
        ("Person::set_name",     "Person::set_name::self"),
        ("Greeter::greet",       "Greeter::greet::self"),
    }
    assert expected.issubset(defs)

def test_inherits_and_has_method(adapted):
    inh = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "inherits"
    }
    assert ("Person", "Greeter") in inh

    hm = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "has_method"
    }
    expected = {
        ("Person",  "Person::__init__"),
        ("Person",  "Person::greet"),
        ("Person",  "Person::set_name"),
        ("Greeter", "Greeter::greet"),
    }
    assert expected.issubset(hm)
