import os
import json
import pytest

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep", "javascript"))

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
    assert person.get("bases") in (["Greeter"], ["index.js::Greeter"], [['Greeter']], None)
    methods = {c["name"] for c in components if c.get("class") == "Person"}
    assert {"constructor", "greet", "set_name"}.issubset(methods)


def test_arrow_function_extraction(components):
    arrows = {c["name"] for c in components if c["kind"] == "arrow_function"}
    assert "add" in arrows
    arrow_func = next(c for c in components if c["kind"] == "arrow_function" and c["name"] == "add")
    assert arrow_func["parameters"] == "(a, b)"
    assert len(arrow_func["function_calls"]) == 0


def test_variable_extraction(components):
    variables = {c["name"] for c in components if c["kind"] == "variable"}
    assert "add" in variables
    assert "p" in variables


def test_import_extraction(components):
    imports = [c for c in components if c["kind"] == "import"]
    assert len(imports) > 0
    # Example check for one import
    util_import = next((i for i in imports if "./utils" in i.get("source", "")), None)
    assert util_import is not None
    assert util_import["details"]["named"][0]["local"] == "greet_user"


def test_export_extraction(components):
    exports = [c for c in components if c["kind"] == "export"]
    assert len(exports) > 0
    # Example check for a default export
    default_export = next((e for e in exports if e.get("default")), None)
    assert default_export is not None
    assert default_export["name"] in ("type_func", "default", "function")


def test_typefunc_return_and_literal(components):
    tf = next(c for c in components if c["kind"] == "function" and c["name"] == "type_func")
    assert "chain complete" in tf.get("code", "")

def test_raw_call_chain(components):
    # raw function_calls from the extractor
    calls = { c["name"]: c.get("function_calls", []) for c in components if c["kind"]=="function" }
    main_calls = [c["function"] for c in calls.get("main", [])]
    assert "func_main" in main_calls
