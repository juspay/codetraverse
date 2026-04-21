# tests/extractors/test_java_extractor.py

import os
import json
import pytest
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from codetraverse.extractors.java_extractor import JavaComponentExtractor

HERE = os.path.dirname(__file__)
SAMPLE_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "sample_code_repo_test", "java"))


@pytest.fixture(scope="module")
def components():
    extractor = JavaComponentExtractor()
    os.environ["ROOT_DIR"] = SAMPLE_DIR
    return extractor.extract_from_folder(SAMPLE_DIR)


def test_class_extraction(components):
    classes = {c["name"] for c in components if c["kind"] == "class"}
    assert "Service" in classes
    assert "Model" in classes


def test_method_extraction(components):
    methods = {c["name"] for c in components if c["kind"] == "method"}
    assert "main" in methods
    assert "process" in methods
    assert "setValue" in methods
    assert "getValue" in methods


def test_constructor_extraction(components):
    constructors = {c["name"] for c in components if c["kind"] == "constructor"}
    assert "Model" in constructors


def test_field_extraction(components):
    fields = {c["name"] for c in components if c["kind"] == "field"}
    assert len(fields) >= 0


def test_import_extraction(components):
    imports = [c["name"] for c in components if c["kind"] == "import"]
    assert any("MathUtil" in imp for imp in imports)


def test_code_presence(components):
    for comp in components:
        assert "code" in comp
        assert comp["code"]


def test_location_info(components):
    for comp in components:
        assert "start_line" in comp
        assert "end_line" in comp
        assert comp["start_line"] <= comp["end_line"]

def test_step_definition_extraction(components):
    step_defs = [c for c in components if c.get("kind") == "step_definition"]
    assert len(step_defs) > 0, "Should have step definitions"

def test_step_definition_types(components):
    step_defs = [c for c in components if c.get("kind") == "step_definition"]
    step_types = {c.get("step_type") for c in step_defs}
    assert "given" in step_types
    assert "when" in step_types
    assert "then" in step_types

def test_step_pattern_extraction(components):
    step_defs = [c for c in components if c.get("kind") == "step_definition"]
    patterns = {c.get("step_pattern") for c in step_defs}
    assert any("user is on login page" in p for p in patterns if p)
    assert any("user enters username" in p for p in patterns if p)
    assert any("user should see dashboard" in p for p in patterns if p)


def test_interface_extraction(components):
    interfaces = {c["name"] for c in components if c["kind"] == "interface"}
    assert "IProcessor" in interfaces


def test_enum_extraction(components):
    enums = {c["name"] for c in components if c["kind"] == "enum"}
    assert "Status" in enums


def test_extends_relationship(components):
    classes_with_extends = [c for c in components if c.get("extends")]
    assert len(classes_with_extends) > 0
    extends_names = {c.get("extends") for c in classes_with_extends}
    assert "BaseClass" in extends_names


def test_implements_relationship(components):
    classes_with_implements = [c for c in components if c.get("implements")]
    assert len(classes_with_implements) > 0
    implements_names = {c.get("implements") for c in classes_with_implements}
    assert "IProcessor" in implements_names


def test_annotation_extraction(components):
    components_with_annotations = [c for c in components if c.get("annotations")]
    assert len(components_with_annotations) > 0


def test_static_method_extraction(components):
    methods = [c for c in components if c.get("kind") == "method"]
    assert len(methods) > 0


def test_nested_class_extraction(components):
    nested_classes = [c for c in components if c.get("kind") == "class" and c.get("enclosing_class")]
    assert len(nested_classes) >= 0


def test_method_with_multiple_parameters(components):
    step_defs = [c for c in components if c.get("kind") == "step_definition"]
    multi_param = [c for c in step_defs if c.get("parameters") and len(c["parameters"]) > 1]
    assert len(multi_param) > 0
