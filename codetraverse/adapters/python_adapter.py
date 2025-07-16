def adapt_python_components(raw_components, quiet=True):
    nodes = []
    edges = []

    def add_node(name, category, extra=None):
        node = {"id": name, "category": category}
        if extra:
            node.update(extra)
        if name not in seen_nodes:
            seen_nodes[name] = node
            nodes.append(node)
        return node

    seen_nodes = {}

    for comp in raw_components:
        if comp["kind"] == "function":
            fn_node = add_node(comp["name"], "function", {
                "signature": comp.get("parameters", []),
                "location": {
                    "start": comp["start_line"],
                    "end": comp["end_line"]
                }
            })

            for call in comp.get("function_calls", []):
                add_node(call, "function")
                edges.append({
                    "from": comp["name"],
                    "to": call,
                    "relation": "calls"
                })

            # embed parameters and any inferred variable references
            for param in comp.get("parameters", []):
                add_node(f"{comp['name']}::{param}", "parameter")
                edges.append({
                    "from": comp["name"],
                    "to": f"{comp['name']}::{param}",
                    "relation": "defines"
                })

        elif comp["kind"] == "class":
            class_node = add_node(comp["name"], "class", {
                "location": {
                    "start": comp["start_line"],
                    "end": comp["end_line"]
                }
            })

            for base in comp.get("base_classes", []):
                add_node(base, "class")
                edges.append({
                    "from": comp["name"],
                    "to": base,
                    "relation": "inherits"
                })

            for method in comp.get("methods", []):
                method_node = add_node(f"{comp['name']}::{method['name']}", "method", {
                    "signature": method.get("parameters", []),
                    "location": {
                        "start": method["start_line"],
                        "end": method["end_line"]
                    }
                })

                edges.append({
                    "from": comp["name"],
                    "to": f"{comp['name']}::{method['name']}",
                    "relation": "has_method"
                })

                for call in method.get("function_calls", []):
                    add_node(call, "function")
                    edges.append({
                        "from": f"{comp['name']}::{method['name']}",
                        "to": call,
                        "relation": "calls"
                    })

                for param in method.get("parameters", []):
                    add_node(f"{comp['name']}::{method['name']}::{param}", "parameter")
                    edges.append({
                        "from": f"{comp['name']}::{method['name']}",
                        "to": f"{comp['name']}::{method['name']}::{param}",
                        "relation": "defines"
                    })

    return {"nodes": nodes, "edges": edges}
