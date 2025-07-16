import os
import json
import pytest

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep", "golang"))

@pytest.fixture(scope="module")
def components():
    comps = []
    for fname in ("main.json", "models.json", "types.json", "utils.json"):
        path = os.path.join(FDEP_DIR, fname)
        with open(path, encoding="utf-8") as f:
            comps.extend(json.load(f))
    return comps

def test_function_extraction(components):
    fnames = {c.get("name") for c in components if c.get("kind") == "function"}
    expected = {
        "main", "FuncMain",
        "GreetUser", "UtilFunc",
        "Print", "ModelFunc",
        "TypeFunc"
    }
    assert expected.issubset(fnames)

def test_method_extraction(components):
    methods = {
        (c.get("receiver_type"), c.get("name"))
        for c in components if c.get("kind") == "method"
    }
    assert ("Person", "Greet") in methods
    assert ("Person", "SetName") in methods

def test_struct_fields_keys(components):
    person = next(c for c in components
                  if c.get("kind") == "struct" and c.get("name") == "Person")
    # The extractor always emits 'fields' and 'field_types' as lists,
    # even if currently empty.
    assert "fields" in person and isinstance(person["fields"], list)
    assert "field_types" in person and isinstance(person["field_types"], list)

def test_typefunc_return_and_literal(components):
    tf = next(c for c in components if c.get("name") == "TypeFunc")
    assert tf.get("return_type") == "string"
    assert "\"chain complete\"" in tf.get("literals", [])

def test_raw_call_extraction(components):
    main_fn = next(c for c in components
                   if c.get("kind") == "function" and c.get("name") == "main")
    # It should list the raw call "FuncMain"
    assert "FuncMain" in main_fn.get("function_calls", [])

    util_fn = next(c for c in components
                   if c.get("kind") == "function" and c.get("name") == "UtilFunc")
    # It should list the raw call "models.ModelFunc"
    assert "models.ModelFunc" in util_fn.get("function_calls", [])

def test_chain_functions_extracted(components):
    """
    Verifies that all four chain functions have been extracted:
      FuncMain, UtilFunc, ModelFunc, TypeFunc
    and that TypeFunc has the expected return_type and literal.
    """
    fnames = {c["name"] for c in components if c.get("kind") == "function"}
    for fn in ("FuncMain", "UtilFunc", "ModelFunc", "TypeFunc"):
        assert fn in fnames, f"{fn} not extracted as function"

    # And check TypeFunc specifically
    tf = next(c for c in components if c.get("name") == "TypeFunc")
    assert tf.get("return_type") == "string", "TypeFunc should return string"
    assert "\"chain complete\"" in tf.get("literals", []), "TypeFunc literal missing"

