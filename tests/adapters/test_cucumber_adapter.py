# tests/adapters/test_cucumber_adapter.py

import os
import json
import pytest
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from codetraverse.extractors.cucumber_extractor import CucumberComponentExtractor
from codetraverse.adapters.cucumber_adapter import adapt_cucumber_components

HERE = os.path.dirname(__file__)
SAMPLE_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "sample_code_repo_test", "cucumber"))


@pytest.fixture(scope="module")
def adapted():
    extractor = CucumberComponentExtractor()
    os.environ["ROOT_DIR"] = SAMPLE_DIR
    components = extractor.extract_from_folder(SAMPLE_DIR)
    return adapt_cucumber_components(components)


def test_nodes_and_edges_structure(adapted):
    assert isinstance(adapted, dict)
    assert isinstance(adapted["nodes"], list)
    assert isinstance(adapted["edges"], list)


def test_feature_nodes_exist(adapted):
    categories = {n["category"] for n in adapted["nodes"]}
    assert "feature" in categories


def test_scenario_nodes_exist(adapted):
    categories = {n["category"] for n in adapted["nodes"]}
    assert "scenario" in categories


def test_feature_id_format(adapted):
    feature_nodes = [n for n in adapted["nodes"] if n["category"] == "feature"]
    for node in feature_nodes:
        assert "::" in node["id"]
        assert "Feature" in node["id"]


def test_contains_edges_exist(adapted):
    contains_edges = [e for e in adapted["edges"] if e["relation"] == "contains"]
    assert len(contains_edges) > 0


def test_node_ids_have_file_path(adapted):
    for node in adapted["nodes"]:
        assert "::" in node["id"]


def test_location_info_in_nodes(adapted):
    for node in adapted["nodes"]:
        assert "location" in node
        assert "start" in node["location"]
        assert "end" in node["location"]


def test_scenario_has_tags(adapted):
    scenario_nodes = [n for n in adapted["nodes"] if n["category"] == "scenario"]
    assert any("tags" in n for n in scenario_nodes)
