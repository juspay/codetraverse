# import os
# import pytest
# from codetraverse.extractors.go_extractor import GoComponentExtractor
# from codetraverse.adapters.go_adapter import adapt_go_components

# @pytest.fixture(scope="module")
# def graph():
#     root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sample_code_repo_test", "golang"))
#     extractor = GoComponentExtractor()
#     raw = []
#     for fname in ["main.go", "models.go", "utils.go", "types.go"]:
#         extractor.process_file(os.path.join(root, fname))
#         raw.extend(extractor.extract_all_components())
#     return adapt_go_components(raw)

# def test_nodes_and_edges_structure(graph):
#     assert isinstance(graph, dict)
#     assert "nodes" in graph and "edges" in graph
#     assert isinstance(graph["nodes"], list)
#     assert isinstance(graph["edges"], list)

# def test_core_nodes_present(graph):
#     ids = {n["id"] for n in graph["nodes"]}
#     expected = {
#         "main.go::main",
#         "utils.go::GreetUser",
#         "models.go::Person",
#         "models.go::Person::Greet",
#         "models.go::Person::SetName",
#         "types.go::Greeter",
#         "types.go::Name",
#         "main.go::AppName",
#         "types.go::AdminRole",
#         "types.go::DefaultRole",
#     }
#     assert expected.issubset(ids)

# def test_calls_edge_exists(graph):
#     calls = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "calls"}
#     assert ("main.go::main", "utils.go::GreetUser") in calls
#     assert ("utils.go::GreetUser", "models.go::Print") in calls

# def test_has_method_edges(graph):
#     has_method = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "has_method"}
#     assert ("models.go::Person", "models.go::Person::Greet") in has_method
#     assert ("models.go::Person", "models.go::Person::SetName") in has_method

# def test_type_alias_edge(graph):
#     type_alias = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "type_alias"}
#     assert ("types.go::Name", "string") in type_alias

# def test_var_type_edges(graph):
#     vtypes = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "var_type"}
#     assert ("main.go::AppName", "string") in vtypes
#     assert ("types.go::DefaultRole", "Role") in vtypes

# def test_interface_dep_edge(graph):
#     ideps = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "interface_dep"}
#     assert ("types.go::Greeter", "string") in ideps

# def test_field_type_edges(graph):
#     ftypes = {(e["from"], e["to"]) for e in graph["edges"] if e["relation"] == "field_type"}
#     assert ("models.go::Person", "int") in ftypes
#     assert ("models.go::Person", "types.Role") in ftypes
