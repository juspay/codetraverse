import os
import pytest
from codetraverse.extractors.haskell_extractor import HaskellComponentExtractor

SAMPLE_DIR = os.path.join("sample_code_repo_test", "haskell")

@pytest.fixture(scope="module")
def components():
    extr = HaskellComponentExtractor()
    comps = []
    for fn in sorted(os.listdir(SAMPLE_DIR)):
        if fn.endswith(".hs"):
            path = os.path.join(SAMPLE_DIR, fn)
            extr.process_file(path)
            comps.extend(extr.extract_all_components())
    return comps

def test_module_headers_present(components):
    headers = [c for c in components if c["kind"] == "module_header"]
    # exactly four modules
    assert len(headers) == 4
    names = {h["name"] for h in headers}
    assert names == {"Main", "Models", "Types", "Utils"}

def test_imports_extraction(components):
    imports = [c for c in components if c["kind"] == "import"]
    # at least one import in each .hs
    files = {os.path.basename(c["file_path"]) for c in imports}
    assert files == {"Main.hs", "Models.hs", "Types.hs", "Utils.hs"}

def test_data_types_and_classes(components):
    dt = {
        (os.path.basename(c["file_path"]), c["kind"], c["name"])
        for c in components
        if c["kind"] in ("data_type", "class", "instance")
    }
    expected = {
        ("Models.hs", "data_type", "User"),
        ("Models.hs", "instance",  "Greeter"),
        ("Utils.hs",  "data_type", "MyClass"),
        ("Utils.hs",  "class",     "Greeter"),
        ("Utils.hs",  "instance",  "Greeter"),
    }
    assert expected <= dt

def test_functions_extracted(components):
    fns = {c["name"] for c in components if c["kind"] == "function"}
    # only these three are actually picked up
    assert fns == {"helper", "newMethod", "capitalizeWords"}

def test_where_clause_extraction(components):
    # These two functions in our sample have `where`-clauses in the .hs files
    for fname in ("helper", "capitalizeWords"):
        comp = next(c for c in components if c["kind"] == "function" and c["name"] == fname)
        assert "where" in comp["code"], f"{fname!r} should contain a where-clause in its code"



def test_instance_methods_key(components):
    insts = [c for c in components if c["kind"] == "instance"]
    # extractor always emits the key, even if empty
    assert all("instance_methods" in i for i in insts)
