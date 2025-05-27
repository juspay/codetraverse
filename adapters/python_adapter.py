# adapters/python_adapter.py

def adapt_python_components(raw_components):
    """
    Convert raw Python extractor output into the unified {nodes, edges} schema.
    Handles both dict-based calls and simple string entries.
    """
    nodes = []
    edges = []

    for comp in raw_components:
        # 1) Node for the function or class
        nodes.append({
            "id":       comp["name"],
            "category": comp.get("kind", "unknown"),
            "signature": None,  # Python has no explicit type signatures
            "location": {
                "start": comp.get("start_line"),
                "end":   comp.get("end_line")
            }
        })

        # 2) If this is a class, also create nodes/edges for its methods
        if comp["kind"] == "class":
            for method in comp.get("methods", []):
                # method node
                nodes.append({
                    "id":       method["name"],
                    "category": "function",
                    "signature": None,
                    "location": {
                        "start": method.get("start_line"),
                        "end":   method.get("end_line")
                    }
                })
                # edge: class → method (defines)
                edges.append({
                    "from":     comp["name"],
                    "to":       method["name"],
                    "relation": "defines"
                })
                # calls within the method
                for call in method.get("function_calls", []):
                    callee = call["name"] if isinstance(call, dict) else call
                    edges.append({
                        "from":     method["name"],
                        "to":       callee,
                        "relation": "calls"
                    })

        # 3) Edges for top-level function calls
        if comp["kind"] == "function":
            for call in comp.get("function_calls", []):
                callee = call["name"] if isinstance(call, dict) else call
                edges.append({
                    "from":     comp["name"],
                    "to":       callee,
                    "relation": "calls"
                })

    # 4) Add any referenced but undeclared nodes as "unknown"
    seen = {n["id"] for n in nodes}
    for e in edges:
        for node_id in (e["from"], e["to"]):
            if node_id not in seen:
                nodes.append({
                    "id":       node_id,
                    "category": "unknown",
                    "signature": None,
                    "location": {"start": None, "end": None}
                })
                seen.add(node_id)

    return {"nodes": nodes, "edges": edges}
