import os
import json
import pytest

HERE = os.path.dirname(__file__)
FDEP_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "output", "fdep"))

@pytest.fixture(scope="module")
def components():
    comps = []
    # Try to find extracted JSON files
    java_dir = FDEP_DIR
    if os.path.isdir(java_dir):
        for fname in os.listdir(java_dir):
            if fname.endswith(".json"):
                path = os.path.join(java_dir, fname)
                with open(path, encoding="utf-8") as f:
                    comps.extend(json.load(f))
    return comps

def test_class_extraction(components):
    """Test that classes are extracted correctly."""
    class_names = {c.get("name") for c in components if c.get("kind") == "class"}
    expected_classes = {"Main", "UserService", "User"}
    for cls in expected_classes:
        assert cls in class_names, f"{cls} not extracted as class"

def test_method_extraction(components):
    """Test that methods are extracted correctly."""
    method_names = {c.get("name") for c in components if c.get("kind") == "method"}
    expected_methods = {"main", "run", "setupDriver", "cleanup", "initialize", 
                       "createUser", "findUserById", "updateUser", "deleteUser",
                       "getId", "setId", "getName", "setName", "getEmail", "setEmail",
                       "isActive", "setActive"}
    for method in expected_methods:
        assert method in method_names, f"{method} not extracted as method"

def test_constructor_extraction(components):
    """Test that constructors are extracted correctly."""
    constructors = {c.get("name") for c in components if c.get("kind") == "constructor"}
    assert "Main" in constructors
    assert "User" in constructors

def test_field_extraction(components):
    """Test that class fields are extracted."""
    user_class = next((c for c in components 
                      if c.get("kind") == "class" and c.get("name") == "User"), None)
    assert user_class is not None, "User class not found"
    assert "fields" in user_class
    assert len(user_class["fields"]) > 0

def test_package_extraction(components):
    """Test that package is extracted."""
    file_comp = next((c for c in components if c.get("kind") == "file"), None)
    assert file_comp is not None
    assert file_comp.get("package") == "com.example"

def test_imports_extraction(components):
    """Test that imports are extracted."""
    file_comp = next((c for c in components if c.get("kind") == "file"), None)
    assert file_comp is not None
    # Note: sample Java files don't have imports, but the field should exist
    assert "imports" in file_comp

def test_function_calls_extraction(components):
    """Test that function calls within methods are extracted."""
    main_method = next((c for c in components 
                       if c.get("kind") == "method" and c.get("name") == "main"), None)
    assert main_method is not None
    # Should have calls to Main() constructor and app.run()
    calls = main_method.get("function_calls", [])
    assert len(calls) > 0

def test_return_type_extraction(components):
    """Test that return types are extracted correctly."""
    find_user_method = next((c for c in components 
                            if c.get("kind") == "method" and c.get("name") == "findUserById"), None)
    assert find_user_method is not None
    assert find_user_method.get("return_type") == "User"