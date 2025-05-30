def adapt_rescript_components(raw_components):
    """
    Transforms raw Tree-Sitter–extracted ReScript components into a unified
    graph schema of nodes and edges.
    """
    nodes = []
    edges = []

    # 1) Create a node for each component
    for comp in raw_components:
        kind = comp.get("kind")
        name = comp.get("name")
        node = {
            "id": name,
            "category": kind,
            "start_line": comp.get("start_line"),
            "end_line": comp.get("end_line"),
            # attach type annotation or subkind if present
            "signature": comp.get("type_annotation") or comp.get("subkind"),
        }

        # for modules and types, also record code snippet length
        if kind in ("module", "type"):
            node["snippet_length"] = len(comp.get("code", ""))

        # for value/external declarations, record raw code
        if kind in ("external", "variable"):
            node["raw_code"] = comp.get("code")

        nodes.append(node)

    # 2) Build edges for function/value bindings
    for comp in raw_components:
        src = comp.get("name")
        # calls
        for fn in comp.get("function_calls", []):
            edges.append({
                "from":     src,
                "to":       fn,
                "relation": "calls"
            })
        # nested/module containment
        if comp.get("kind") == "module":
            for child in comp.get("elements", []):
                edges.append({
                    "from":     src,
                    "to":       child.get("name"),
                    "relation": "contains"
                })

    # 3) Unknown nodes: any target of an edge not yet declared
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
