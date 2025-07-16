import os
import json
import pytest

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep", "typescript"))

@pytest.fixture(scope="module")
def components():
    comps = []
    for fname in ("index.json", "models.json", "types.json", "utils.json"):
        path = os.path.join(FDEP_DIR, fname)
        with open(path, encoding="utf-8") as f:
            comps.extend(json.load(f))
    return comps


def test_imports_and_exports_present(components):
    kinds = {c.get("kind") for c in components}
    assert "import" in kinds
    assert "export" in kinds


def test_function_declarations(components):
    fn_names = {c["name"] for c in components if c.get("kind") == "function"}
    expected = {
        "func1", "func2", "func3",
        "greetUser", "defaultGreet",
        "log", "getUserAlias", "logSomething",
        "main", "nsFunc"
    }
    assert expected.issubset(fn_names)


def test_class_and_method_extraction(components):
    classes = {c["name"] for c in components if c.get("kind") == "class"}
    assert {"Person", "Admin", "ChainClass"}.issubset(classes)

    methods = {
        (c.get("parent"), c["name"])
        for c in components
        if c.get("kind") == "method"
    }
    assert ("ChainClass", "finalMethod") in methods
    assert ("Person", "greet") in methods
    assert ("Admin", "promote") in methods


def test_field_getter_setter(components):
    fields = {c["name"] for c in components if c.get("kind") == "field"}
    assert "instanceCount" in fields
    assert "createdAt" in fields

    getters = [c for c in components if c.get("getter") is True]
    setters = [c for c in components if c.get("setter") is True]
    assert any(c["name"] == "role" for c in getters)
    assert any(c["name"] == "role" for c in setters)


def test_interface_and_enum(components):
    interfaces = {c["name"] for c in components if c.get("kind") == "interface"}
    assert {"User", "BaseUser", "Timestamped"}.issubset(interfaces)

    enums = [c for c in components if c.get("kind") == "enum" and c["name"] == "Status"]
    assert enums, "Status enum not found"
    status_members = {m["value"] for m in enums[0]["members"]}
    assert status_members == {"'active'", "'inactive'", "'pending'"}


def test_type_alias_and_literals(components):
    # union alias Role → literal_type AST nodes for 'admin' and 'user'
    lit_values = {c["value"] for c in components if c.get("kind") == "literal_type"}
    assert "'admin'" in lit_values
    assert "'user'" in lit_values

    # conditional alias → literal_type AST nodes for 'a','yes','no'
    for v in ("'a'", "'yes'", "'no'"):
        assert v in lit_values, f"{v} not extracted as literal_type"

    # also check the Role type_alias lists these as literal_type_dependencies
    role_alias = next(c for c in components
                      if c.get("kind") == "type_alias" and c["name"] == "Role")
    deps = set(role_alias.get("literal_type_dependencies", []))
    assert deps == {"'admin'", "'user'"}


def test_keyof_and_typeof(components):
    keyofs = [c for c in components if c.get("operator") == "keyof"]
    assert any(c["target"] == "User" for c in keyofs)

    typeofs = [c for c in components if c.get("operator") == "typeof"]
    targets = {c["target"] for c in typeofs}
    assert "APP_NAME" in targets
    assert "DEFAULT_USER" in targets


def test_generator_and_arrow(components):
    # arrow‐function value should contain =>
    arrows = [c for c in components if c.get("kind") == "arrow_function"]
    assert any(c["name"] == "arrowFn" and "=>" in c.get("value", "")
               for c in arrows)

    # both generator functions should be present
    gens = {c["name"] for c in components
            if c.get("kind") == "generator_function_declaration"}
    assert {"genNumbers", "asyncGen"}.issubset(gens)


def test_function_calls_extracted(components):
    # greetUser must call aliasGet
    greet = next(c for c in components
                 if c.get("kind") == "function" and c["name"] == "greetUser")
    called = {call["base_name"] for call in greet.get("function_calls", [])}
    assert "aliasGet" in called

    # top‐level console.log in utils.ts should include the literal argument
    top_calls = [c for c in components
                 if c.get("kind") == "function_call" and c.get("module") == "utils.ts"]
    assert any(
        "'ChainClass.finalMethod invoked'" in c.get("arguments", [])
        for c in top_calls
    )

    # ensure the c.finalMethod call inside func3() is captured
    assert any(
        c.get("kind") == "function_call"
        and c.get("module") == "types.ts"
        and c.get("object") == "c"
        and c.get("method") == "finalMethod"
        for c in components
    )
