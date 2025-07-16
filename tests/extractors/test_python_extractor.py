# tests/extractors/test_python_extractor.py

import os
import json
import pytest

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep", "python"))

@pytest.fixture(scope="module")
def components():
    comps = []
    for fname in ("index.json", "models.json", "types.json", "utils.json"):
        path = os.path.join(FDEP_DIR, fname)
        with open(path, encoding="utf-8") as f:
            comps.extend(json.load(f))
    return comps

def test_function_extraction(components):
    fnames = {c["name"] for c in components if c["kind"] == "function"}
    for fn in ("main", "func_main", "greet_user",
               "util_func", "print_person",
               "model_func", "type_func"):
        assert fn in fnames

def test_class_extraction(components):
    cls = {c["name"] for c in components if c["kind"] == "class"}
    assert {"Person", "Greeter"}.issubset(cls)

def test_person_class_details(components):
    person = next(c for c in components if c["kind"] == "class" and c["name"] == "Person")
    # inheritance
    assert person.get("base_classes") == ["Greeter"]
    # methods
    methods = {m["name"] for m in person.get("methods", [])}
    assert {"__init__", "greet", "set_name"}.issubset(methods)

def test_typefunc_return_and_literal(components):
    tf = next(c for c in components if c["kind"] == "function" and c["name"] == "type_func")
    assert tf.get("return_type") == "str"
    assert "\"chain complete\"" in tf.get("literals", [])

def test_raw_call_chain(components):
    # raw function_calls from the extractor
    calls = { c["name"]: c.get("function_calls", []) for c in components if c["kind"]=="function" }
    assert "func_main"   in calls["main"]
    assert "util_func"   in calls["func_main"]
    assert "model_func"  in calls["util_func"]
    assert "type_func"   in calls["model_func"]
