import os
import json
import pytest
from codetraverse.adapters.haskell_adapter import adapt_haskell_components

# point this at your raw JSON f-dep outputs (or your sample_code_repo_test copies)
FDEP_DIR = os.path.join("output", "fdep", "haskell")

# load all four .json files
@pytest.fixture(scope="module")
def graph():
    raw = []
    for fn in ("Main.json", "Models.json", "Types.json", "Utils.json"):
        path = os.path.join(FDEP_DIR, fn)
        with open(path, encoding="utf-8") as f:
            raw.extend(json.load(f))
    return adapt_haskell_components(raw)


def test_nodes_and_edges_structure(graph):
    # top‐level shape
    assert "nodes" in graph and "edges" in graph

    # every node must at least have these four…
    required = {"id", "category", "name", "file_path"}
    for n in graph["nodes"]:
        assert required.issubset(n)
        # …and non‐external nodes must have a location
        if n["category"] != "external":
            assert "location" in n



def test_core_nodes_present(graph):
    ids = {n["id"] for n in graph["nodes"]}

    expected = {
        # module headers
        "Main::Main", "Models::Models", "Types::Types", "Utils::Utils",
        # data types & typeclasses/instances
        "Models::User", "Models::Greeter",
        "Utils::MyClass", "Utils::Greeter",
        # top-level functions
        "Types::helper", "Utils::newMethod", "Utils::capitalizeWords",
    }
    assert expected <= ids


def test_calls_edge_exists(graph):
    calls = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "calls"}

    # helper → its where-binding y
    assert ("Types::helper", "Types::y") in calls

    # newMethod → its local vars
    for target in ("Utils::x", "Utils::+", "Utils::1", "Utils::y"):
        assert ("Utils::newMethod", target) in calls

    # capitalizeWords → its library calls
    assert ("Utils::capitalizeWords", "Utils::unwords") in calls


def test_uses_type_edges(graph):
    uses = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "uses_type"}

    assert ("Types::helper", "Types::Int") in uses
    assert ("Utils::newMethod", "Utils::Int") in uses
    assert ("Utils::capitalizeWords", "Utils::String") in uses


def test_implements_edge(graph):
    impls = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "implements"}

    # The current adaptor emits reflexive implements for both
    assert ("Models::Greeter", "Models::Greeter") in impls
    assert ("Utils::Greeter",  "Utils::Greeter")  in impls
