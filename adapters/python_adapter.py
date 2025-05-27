# adapters/python_adapter.py

def adapt_python_components(raw_components):
    nodes = []
    edges = []

    for comp in raw_components:
        nodes.append({
            "id":       comp["name"],
            "category": comp.get("kind", "unknown"),
            "signature": None,
            "location": {
                "start": comp.get("start_line"),
                "end":   comp.get("end_line")
            }
        })

        if comp["kind"] == "class":
            for method in comp.get("methods", []):
                nodes.append({
                    "id":       method["name"],
                    "category": "function",
                    "signature": None,
                    "location": {
                        "start": method.get("start_line"),
                        "end":   method.get("end_line")
                    }
                })
                edges.append({
                    "from":     comp["name"],
                    "to":       method["name"],
                    "relation": "defines"
                })
                for call in method.get("function_calls", []):
                    callee = call["name"] if isinstance(call, dict) else call
                    edges.append({
                        "from":     method["name"],
                        "to":       callee,
                        "relation": "calls"
                    })

        if comp["kind"] == "function":
            for call in comp.get("function_calls", []):
                callee = call["name"] if isinstance(call, dict) else call
                edges.append({
                    "from":     comp["name"],
                    "to":       callee,
                    "relation": "calls"
                })

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
