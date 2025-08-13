import os
import json
import pytest
from codetraverse.adapters.javascript_adapter import adapt_javascript_components

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep", "javascript"))

@pytest.fixture(scope="module")
def adapted():
    raw_components = []
    for fname in ("index.json", "models.json", "types.json", "utils.json"):
        path = os.path.join(FDEP_DIR, fname)
        with open(path, encoding="utf-8") as f:
            raw_components.extend(json.load(f))
    return adapt_javascript_components(raw_components)

def test_nodes_and_edges_structure(adapted):
    assert isinstance(adapted, dict)
    assert isinstance(adapted["nodes"], list)
    assert isinstance(adapted["edges"], list)

def test_core_nodes_present(adapted):
    ids = {n["id"] for n in adapted["nodes"]}
    # classes
    assert any("Person" in i for i in ids)
    assert any("Greeter" in i for i in ids)
    # free functions
    for fn in ("main", "func_main", "greet_user", "util_func",
               "print_person", "model_func", "type_func"):
        assert any(fn in i for i in ids), f"Expected function node {fn}"
    # methods
    for m in ("Person::greet", "Person::set_name", "Greeter::greet"):
        assert any(i.endswith(m) for i in ids), f"Expected method node {m}"
    assert any("Person::constructor" in i for i in ids)

def test_call_edges(adapted):
    calls = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "calls"
    }
    expected = {
        ("javascript/index.js::main", "javascript/utils.js::greet_user"),
        ("javascript/index.js::main", "javascript/index.js::func_main"),
        ("javascript/utils.js::greet_user", "javascript/utils.js::print_person"),
        ("javascript/utils.js::util_func", "javascript/models.js::model_func"),
        ("javascript/models.js::model_func", "javascript/types.js::function"),
    }
    assert expected.issubset(calls)

def test_inherits_and_has_method(adapted):
    relations = {(e["from"], e["to"], e["relation"]) for e in adapted["edges"]}
    
    # Inheritance
    assert ("javascript/models.js::Person", "javascript/index.js::Greeter", "extends") in relations
    
    # Containment
    assert ("javascript/models.js::Person", "javascript/models.js::Person::constructor", "calls") in relations
    assert ("javascript/models.js::Person", "javascript/models.js::Person::greet", "calls") in relations


def test_instantiation_edges(adapted):
    edges = adapted["edges"]
    instantiates = {(e["from"], e["to"]) for e in edges if e["relation"] == "instantiates"}
    
    # main function instantiates Person
    assert any("main" in f and "Person" in t for f, t in instantiates)

    # Check for the corresponding call to the constructor
    calls = {(e["from"], e["to"]) for e in edges if e["relation"] == "calls"}
    assert any("main" in f and "Person::constructor" in t for f, t in calls)


def test_fdep_edges(adapted):
    fdeps = {(e["from"], e["to"]) for e in adapted["edges"] if e["relation"] == "fdeps"}
    
    # index.js depends on utils.js and models.js
    assert ("javascript/index.js", "javascript/utils.js") in fdeps
    assert ("javascript/index.js", "javascript/models.js") in fdeps
    
    # utils.js depends on models.js
    assert ("javascript/utils.js", "javascript/models.js") in fdeps
    
    # models.js depends on types.js
    assert ("javascript/models.js", "javascript/types.js") in fdeps
