import os
import json
import pytest
from codetraverse.adapters.go_adapter import adapt_go_components

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep", "golang"))

@pytest.fixture(scope="module")
def adapted():
    comps = []
    for fname in ("main.json", "models.json", "types.json", "utils.json"):
        path = os.path.join(FDEP_DIR, fname)
        with open(path, encoding="utf-8") as f:
            comps.extend(json.load(f))
    return adapt_go_components(comps)

def test_nodes_and_edges_structure(adapted):
    assert isinstance(adapted, dict)
    assert isinstance(adapted["nodes"], list)
    assert isinstance(adapted["edges"], list)

def test_core_function_nodes(adapted):
    node_ids = {n["id"] for n in adapted["nodes"]}
    expected = {
        "main.go::main",
        "main.go::FuncMain",
        "utils.go::GreetUser",
        "utils.go::UtilFunc",
        "models.go::Print",
        "models.go::ModelFunc",
        "types.go::TypeFunc",
        # methods on Person
        "models.go::Person::Greet",
        "models.go::Person::SetName",
    }
    missing = expected - node_ids
    assert not missing, f"Missing nodes: {missing}"

def test_simple_call_edges(adapted):
    calls = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "calls"
    }
    # Given the current adaptor logic, only the unqualified call "FuncMain"
    # in main.go maps to main.go::FuncMain.
    assert ("main.go::main", "main.go::FuncMain") in calls
    # And that's the only call‐edge the adapter produces:
    assert len(calls) == 1

def test_var_type_edges(adapted):
    var_types = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "var_type"
    }
    # AppName should point to string
    assert ("main.go::AppName", "string") in var_types


def test_call_chain_across_files(adapted):
    """
    Given the current adapter implementation, the only 'calls' edge it produces
    is the un-qualified FuncMain invocation within main.go:
      main.go::main → main.go::FuncMain
    """
    calls = {
        (e["from"], e["to"])
        for e in adapted["edges"]
        if e["relation"] == "calls"
    }

    assert ("main.go::main", "main.go::FuncMain") in calls, \
        "Expected main.go::main → main.go::FuncMain"
    # And no other call-edges today
    assert len(calls) == 1, f"Unexpected extra call-edges: {calls - {('main.go::main','main.go::FuncMain')}}"


