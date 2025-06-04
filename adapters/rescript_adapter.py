import json
import re
from collections import defaultdict

def adapt_rescript_components(raw_components):
    nodes = []
    edges = []

    def extract_component_name(comp):
        """
        Helper to extract a stable “id” for this component.
        Falls back to tag_name if it’s a JSX node, or “Unknown” if nothing else.
        """
        name = comp.get("name")
        if not name and comp.get("kind") == "jsx":
            name = comp.get("tag_name", "UnknownJSX")
        return name or "Unknown"

    def _json_safe(value):
        """
        If value is a primitive (str, int, bool, float), return as-is.
        Otherwise, JSON‐dump it (so build_graph_from_schema will store it as a JSON string).
        """
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return json.dumps(value)

    def process_component_recursively(comp, parent_name=None):
        """
        - Create a node entry for `comp` that contains EVERY field of `comp` (except “name”),
          plus an “id” = the component’s name. Non‐primitives get JSON‐serialized.
          Also include the source file path (comp["file_name"] or comp["file_path"] if present).
        - Then emit edges for:
            • contains (if parent_name is set)
            • calls (for each entry in comp["function_calls"])
            • uses_literal, defines, renders, imports_*, etc.
        - Recurse into local_variables, jsx_elements, module elements, and variants as before.
        """
        kind = comp.get("kind")
        comp_name = extract_component_name(comp)

        # Build a node dictionary that includes EVERY key/value in comp (except “name”),
        # plus an “id” = comp_name. Non‐primitives get JSON‐serialized via _json_safe().
        node_attrs = {"id": comp_name}
        for (k, v) in comp.items():
            if k == "name":
                continue
            node_attrs[k] = _json_safe(v)

        # Also explicitly pull in file_name or file_path if available
        # (so networkx can store the source file path for each node).
        if comp.get("file_name") is not None:
            node_attrs["file_path"] = comp["file_name"]
        elif comp.get("file_path") is not None:
            node_attrs["file_path"] = comp["file_path"]

        nodes.append(node_attrs)

        # If this component is nested under a parent, emit a “contains” edge
        if parent_name:
            edges.append({
                "from": parent_name,
                "to": comp_name,
                "relation": "contains"
            })

        # “calls” edges: for each entry in comp["function_calls"]
        for fn_call in comp.get("function_calls", []):
            if isinstance(fn_call, dict):
                target = fn_call.get("name", str(fn_call))
            elif isinstance(fn_call, str):
                target = fn_call
            else:
                target = str(fn_call)

            target = target.strip()
            if target and target != comp_name:
                edges.append({
                    "from": comp_name,
                    "to": target,
                    "relation": "calls"
                })

        # “uses_literal” edges: for each literal in comp["literals"],
        # if it’s not just a short string/number/boolean.
        for literal in comp.get("literals", []):
            if isinstance(literal, str):
                lit_trim = literal.strip()
                if (lit_trim and
                    len(lit_trim) > 2 and
                    not lit_trim.startswith('"') and
                    not lit_trim.isdigit() and
                    lit_trim not in ["true", "false", "()"]):
                    edges.append({
                        "from": comp_name,
                        "to": f"literal_{lit_trim}",
                        "relation": "uses_literal"
                    })

        # “defines” edges: for any nested local_variables
        for local_var in comp.get("local_variables", []):
            if isinstance(local_var, dict):
                local_name = extract_component_name(local_var)
                edges.append({
                    "from": comp_name,
                    "to": local_name,
                    "relation": "defines"
                })
                # Recurse into that nested variable
                process_component_recursively(local_var, comp_name)

        # “renders” edges: for any nested JSX elements
        for jsx_elem in comp.get("jsx_elements", []):
            if isinstance(jsx_elem, dict):
                jsx_name = extract_component_name(jsx_elem)
                edges.append({
                    "from": comp_name,
                    "to": jsx_name,
                    "relation": "renders"
                })
                process_component_recursively(jsx_elem, comp_name)

        # If this is a “module”, recurse into its “elements”
        if kind == "module":
            for element in comp.get("elements", []):
                if isinstance(element, dict):
                    process_component_recursively(element, comp_name)

        # If this is a “jsx” node, it might have “children_jsx”
        if kind == "jsx":
            for child_jsx in comp.get("children_jsx", []):
                if isinstance(child_jsx, dict):
                    process_component_recursively(child_jsx, comp_name)

        # If this is a “type”, emit “defines_variant” edges
        if kind == "type":
            for variant in comp.get("variants", []):
                if isinstance(variant, dict):
                    var_name = variant.get("name")
                    if var_name:
                        edges.append({
                            "from": comp_name,
                            "to": var_name,
                            "relation": "defines_variant"
                        })

    # Build nodes + edges by walking every top‐level component
    for comp in raw_components:
        process_component_recursively(comp)

    # Step 2: Any endpoint in edges that didn’t appear in nodes → add a “stub” node
    seen_node_ids = {n["id"] for n in nodes}
    for edge in edges:
        for endpoint in (edge["from"], edge["to"]):
            if endpoint not in seen_node_ids:
                # guess a category
                category = "external_reference"
                if endpoint.startswith("literal_"):
                    category = "literal"
                elif "." in endpoint:
                    category = "module_function"
                elif edge["relation"] == "calls":
                    category = "external_function"

                nodes.append({
                    "id": endpoint,
                    "category": category
                })
                seen_node_ids.add(endpoint)

    # Step 3: Emit import‐related edges for each component’s import_map
    for comp in raw_components:
        comp_name = extract_component_name(comp)
        import_map = comp.get("import_map", {})
        for module_name, import_list in import_map.items():
            for import_info in import_list:
                import_type = import_info.get("type", "unknown")
                edges.append({
                    "from": comp_name,
                    "to": module_name,
                    "relation": f"imports_{import_type}"
                })

    # Print summary & return schema
    print(f"Created {len(nodes)} nodes and {len(edges)} edges")
    function_call_edges = [e for e in edges if e["relation"] == "calls"]
    literal_edges = [e for e in edges if e["relation"] == "uses_literal"]
    print(f"Function call edges: {len(function_call_edges)}")
    print(f"Literal usage edges: {len(literal_edges)}")

    return {
        "nodes": nodes,
        "edges": edges
    }
