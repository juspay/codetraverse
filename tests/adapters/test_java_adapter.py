import os
import json
import pytest
from codetraverse.adapters.java_adapter import adapt_java_components

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep"))

@pytest.fixture(scope="module")
def components():
    comps = []
    java_dir = FDEP_DIR
    if os.path.isdir(java_dir):
        for fname in os.listdir(java_dir):
            if fname.endswith(".json"):
                path = os.path.join(java_dir, fname)
                with open(path, encoding="utf-8") as f:
                    comps.extend(json.load(f))
    return comps

@pytest.fixture(scope="module")
def schema(components):
    if not components:
        pytest.skip("No components found - run extraction first")
    return adapt_java_components(components)

def test_nodes_created(schema):
    """Test that nodes are created from components."""
    assert "nodes" in schema
    assert len(schema["nodes"]) > 0

def test_edges_created(schema):
    """Test that edges are created from components."""
    assert "edges" in schema
    assert len(schema["edges"]) > 0

def test_class_as_node(schema):
    """Test that classes are converted to nodes."""
    nodes = schema["nodes"]
    node_ids = {n["id"] for n in nodes}
    # Check for class nodes
    class_nodes = [n for n in nodes if n["category"] == "class"]
    assert len(class_nodes) > 0

def test_method_as_node(schema):
    """Test that methods are converted to nodes."""
    nodes = schema["nodes"]
    method_nodes = [n for n in nodes if n["category"] == "method"]
    assert len(method_nodes) > 0

def test_constructor_as_node(schema):
    """Test that constructors are converted to nodes."""
    nodes = schema["nodes"]
    constructor_nodes = [n for n in nodes if n["category"] == "constructor"]
    assert len(constructor_nodes) > 0

def test_method_calls_edge(schema):
    """Test that method call relationships are created."""
    edges = schema["edges"]
    call_edges = [e for e in edges if e.get("relation") == "calls"]
    assert len(call_edges) > 0

def test_has_method_edge(schema):
    """Test that class-method relationships are created."""
    edges = schema["edges"]
    has_method_edges = [e for e in edges if e.get("relation") == "has_method"]
    assert len(has_method_edges) > 0

def test_node_categories(schema):
    """Test that nodes have correct categories."""
    nodes = schema["nodes"]
    categories = {n["category"] for n in nodes}
    expected_categories = {"class", "method", "constructor"}
    for cat in expected_categories:
        assert cat in categories, f"Category {cat} not found"

def test_signature_format(schema):
    """Test that node signatures are properly formatted for known nodes."""
    nodes = schema["nodes"]
    # Only check known nodes (not "unknown" category)
    known_nodes = [n for n in nodes if n.get("category") != "unknown"]
    assert len(known_nodes) > 0
    for node in known_nodes:
        assert "signature" in node
        assert "id" in node
        assert "category" in node
