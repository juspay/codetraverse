# codetraverse/tests/adapters/test_typescript_adapter.py

import os
import json
import pytest
from codetraverse.adapters.typescript_adapter import adapt_typescript_components

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep", "typescript"))

@pytest.fixture(scope="module")
def adapted():
    all_components = []
    for fname in ("index.json", "models.json", "types.json", "utils.json"):
        path = os.path.join(FDEP_DIR, fname)
        with open(path, encoding="utf-8") as f:
            all_components.extend(json.load(f))
    return adapt_typescript_components(all_components)

def test_nodes_and_edges_structure(adapted):
    assert isinstance(adapted, dict)
    assert "nodes" in adapted and isinstance(adapted["nodes"], list)
    assert "edges" in adapted and isinstance(adapted["edges"], list)

def test_core_nodes_present(adapted):
    node_ids = {n["id"] for n in adapted["nodes"]}
    for core in ("index.ts::func1",
                 "models.ts::func2",
                 "types.ts::func3",
                 "utils.ts::ChainClass::finalMethod"):
        assert core in node_ids

def test_type_dependency_edges(adapted):
    deps = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "type_dependency"
    }
    assert ("types.ts::Role", "types.ts::'admin'") in deps
    assert ("types.ts::Role", "types.ts::'user'") in deps

def test_simple_call_edge(adapted):
    calls = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "calls"
    }
    assert ("index.ts::func1", "models.ts::func2") in calls

def test_linear_chain_edges(adapted):
    calls = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "calls"
    }
    #  func1 → func2 → func3 → finalMethod
    assert ("index.ts::func1",  "models.ts::func2")    in calls
    assert ("models.ts::func2", "types.ts::func3")     in calls
    assert ("types.ts::func3",  "types.ts::c.finalMethod") in calls
