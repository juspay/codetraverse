# tests/extractors/test_cucumber_extractor.py

import os
import json
import pytest
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from codetraverse.extractors.cucumber_extractor import CucumberComponentExtractor

HERE = os.path.dirname(__file__)
SAMPLE_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "sample_code_repo_test", "cucumber"))


@pytest.fixture(scope="module")
def components():
    extractor = CucumberComponentExtractor()
    os.environ["ROOT_DIR"] = SAMPLE_DIR
    return extractor.extract_from_folder(SAMPLE_DIR)


def test_feature_extraction(components):
    features = [c for c in components if c["kind"] == "feature"]
    assert len(features) > 0
    assert any(f["name"] == "User Login Feature" for f in features)


def test_scenario_extraction(components):
    scenarios = [c for c in components if c["kind"] == "scenario"]
    assert len(scenarios) > 0


def test_scenario_outline_extraction(components):
    outlines = [c for c in components if c["kind"] == "scenario_outline"]
    assert len(outlines) > 0


def test_feature_tags(components):
    features = [c for c in components if c["kind"] == "feature"]
    assert any(f.get("tags") for f in features)


def test_scenario_tags(components):
    scenarios = [c for c in components if c["kind"] == "scenario"]
    assert any(s.get("tags") for s in scenarios)


def test_steps_extraction(components):
    scenarios = [c for c in components if c["kind"] == "scenario"]
    for scen in scenarios:
        assert scen.get("steps") is not None
        assert len(scen["steps"]) > 0


def test_examples_extraction(components):
    outlines = [c for c in components if c["kind"] == "scenario_outline"]
    for outline in outlines:
        assert outline.get("examples") is not None
        assert len(outline["examples"]) > 0


def test_code_presence(components):
    for comp in components:
        assert "code" in comp


def test_location_info(components):
    for comp in components:
        assert "start_line" in comp
        assert "end_line" in comp


def test_background_steps_extraction(components):
    backgrounds = [c for c in components if c["kind"] == "background"]
    assert len(backgrounds) > 0
    bg_names = {b.get("name") for b in backgrounds}
    assert any("Background" in name for name in bg_names)


def test_background_steps_detail(components):
    backgrounds = [c for c in components if c["kind"] == "background"]
    assert len(backgrounds) > 0
    bg = backgrounds[0]
    assert bg.get("steps") is not None
    assert len(bg["steps"]) > 0


def test_unmapped_steps_extraction(components):
    scenarios = [c for c in components if c["kind"] == "scenario"]
    unmapped_scenario = [s for s in scenarios if "unmapped" in s.get("module", "")]
    assert len(unmapped_scenario) > 0
    for s in unmapped_scenario:
        assert s.get("steps") is not None
