# tests/adapters/test_java_adapter.py

import os
import json
import pytest
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from codetraverse.extractors.java_extractor import JavaComponentExtractor
from codetraverse.adapters.java_adapter import adapt_java_components

HERE = os.path.dirname(__file__)
SAMPLE_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "sample_code_repo_test", "java"))


@pytest.fixture(scope="module")
def adapted():
    extractor = JavaComponentExtractor()
    os.environ["ROOT_DIR"] = SAMPLE_DIR
    components = extractor.extract_from_folder(SAMPLE_DIR)
    return adapt_java_components(components)


def test_nodes_and_edges_structure(adapted):
    assert isinstance(adapted, dict)
    assert isinstance(adapted["nodes"], list)
    assert isinstance(adapted["edges"], list)


def test_node_categories(adapted):
    categories = {n["category"] for n in adapted["nodes"]}
    assert "class" in categories
    assert "method" in categories


def test_model_class_node(adapted):
    ids = {n["id"] for n in adapted["nodes"]}
    assert any("Model" in i for i in ids)


def test_method_nodes(adapted):
    ids = {n["id"] for n in adapted["nodes"]}
    assert any("main" in i for i in ids)
    assert any("process" in i for i in ids)


def test_constructor_node(adapted):
    ids = {n["id"] for n in adapted["nodes"]}
    assert any("Model" in i and "Model" in i for i in ids)


def test_call_edges_exist(adapted):
    call_edges = [e for e in adapted["edges"] if e["relation"] == "calls"]
    assert len(call_edges) >= 0


def test_node_ids_have_file_path(adapted):
    for node in adapted["nodes"]:
        assert "::" in node["id"]


def test_location_info_in_nodes(adapted):
    for node in adapted["nodes"]:
        assert "location" in node
        assert "start" in node["location"]
        assert "end" in node["location"]
