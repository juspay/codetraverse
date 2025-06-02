def adapt_rescript_components(raw_components):
    """
    Transforms raw Tree-Sitter–extracted ReScript components into a unified
    graph schema of nodes and edges.
    """
    nodes = []
    edges = []

    for comp in raw_components:
        kind = comp.get("kind")
        name = comp.get("name")
        node = {
            "id": name,
            "category": kind,
            "start_line": comp.get("start_line"),
            "end_line": comp.get("end_line"),
            "signature": comp.get("type_annotation") or comp.get("subkind"),
        }

        if kind in ("module", "type"):
            node["snippet_length"] = len(comp.get("code", ""))

        if kind in ("external", "variable"):
            node["raw_code"] = comp.get("code")

        nodes.append(node)

    for comp in raw_components:
        src = comp.get("name")
        for fn in comp.get("function_calls", []):
            edges.append({
                "from":     src,
                "to":       fn,
                "relation": "calls"
            })
        if comp.get("kind") == "module":
            for child in comp.get("elements", []):
                edges.append({
                    "from":     src,
                    "to":       child.get("name"),
                    "relation": "contains"
                })

    seen = {n["id"] for n in nodes}
    for e in edges:
        for endpoint in (e["from"], e["to"]):
            if endpoint not in seen:
                nodes.append({
                    "id":       endpoint,
                    "category": "unknown"
                })
                seen.add(endpoint)

    return {"nodes": nodes, "edges": edges}
