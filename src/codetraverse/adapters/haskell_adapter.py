def adapt_haskell_components(raw_components):
    nodes = []
    edges = []
    for comp in raw_components:
        if comp["kind"] == "function":
            nodes.append({
                "id": comp["name"],
                "category": "function",
                "signature": comp.get("type_signature", "").split("::",1)[1].strip() if comp.get("type_signature") else None,
                "location": {
                    "start": comp["start_line"],
                    "end":   comp["end_line"]
                }
            })
            for call in comp.get("function_calls", []):
                target = call["name"]
                edges.append({
                    "from": comp["name"],
                    "to":   target,
                    "relation": "calls"
                })
            for t in comp.get("type_dependencies", []):
                edges.append({
                    "from": comp["name"],
                    "to":   t,
                    "relation": "depends_on"
                })
    seen = {n["id"] for n in nodes}
    for e in edges:
        for end in (e["from"], e["to"]):
            if end not in seen:
                nodes.append({"id": end, "category": "unknown"})
                seen.add(end)
    return {"nodes": nodes, "edges": edges}