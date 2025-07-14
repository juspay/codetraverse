# import os
# import pytest
# from codetraverse.extractors.go_extractor import GoComponentExtractor

# @pytest.fixture(scope="module")
# def components():
#     # point at the sample Go repo
#     root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sample_code_repo_test", "golang"))
#     extractor = GoComponentExtractor()
#     comps = []
#     for fname in ["main.go", "models.go", "utils.go", "types.go"]:
#         path = os.path.join(root, fname)
#         extractor.process_file(path)
#         # accumulate all components from each file
#         comps.extend(extractor.extract_all_components())
#     return comps

# def test_basic_kinds_present(components):
#     kinds = {c["kind"] for c in components}
#     expected = {
#         "file", "function", "method",
#         "struct", "interface", "type_alias",
#         "constant", "variable"
#     }
#     assert expected.issubset(kinds)

# def test_function_declarations(components):
#     fn_names = {c["name"] for c in components if c["kind"] == "function"}
#     # top-level free functions
#     assert {"main", "Print", "GreetUser"}.issubset(fn_names)

# def test_struct_and_methods(components):
#     # Person struct + its attached methods
#     person = next(c for c in components if c["kind"] == "struct" and c["name"] == "Person")
#     # fields
#     field_names = {f["name"] for f in person["fields"]}
#     assert {"ID", "Name", "Role"}.issubset(field_names)
#     # methods listed on the struct
#     assert set(person["methods"]) >= {"Greet", "SetName"}

# def test_interface_extraction(components):
#     greeter = next(c for c in components if c["kind"] == "interface" and c["name"] == "Greeter")
#     # one method Greet() string
#     assert len(greeter["methods"]) == 1
#     m = greeter["methods"][0]
#     assert m["name"] == "Greet"
#     assert m["return_type"] == "string"

# def test_type_alias_and_constants(components):
#     # Name = string
#     alias = next(c for c in components if c["kind"] == "type_alias" and c["name"] == "Name")
#     assert alias["aliased_type"] == "string"
#     # const AdminRole, UserRole
#     consts = {c["name"] for c in components if c["kind"] == "constant"}
#     assert {"AdminRole", "UserRole"}.issubset(consts)
#     # var AppName, DefaultRole
#     vars_ = {c["name"] for c in components if c["kind"] == "variable"}
#     assert {"AppName", "DefaultRole"}.issubset(vars_)

# def test_function_calls(components):
#     # utils.GreetUser calls models.Print and fmt.Sprintf
#     gu = next(c for c in components if c["kind"] == "function" and c["name"] == "GreetUser")
#     calls_gu = set(gu["function_calls"])
#     assert "models.Print" in calls_gu
#     assert "fmt.Sprintf" in calls_gu

#     # Person.Greet calls fmt.Sprintf
#     greet = next(c for c in components if c["kind"] == "method" and c["name"] == "Greet")
#     calls_g = set(greet["function_calls"])
#     assert "fmt.Sprintf" in calls_g

#     # Print function calls fmt.Println
#     pr = next(c for c in components if c["kind"] == "function" and c["name"] == "Print")
#     calls_pr = set(pr["function_calls"])
#     assert "fmt.Println" in calls_pr
