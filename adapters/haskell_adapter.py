def adapt_haskell_components(raw_components):
    nodes = []
    edges = []

    for comp in raw_components:
        if comp["kind"] != "function":
            continue

        module_name = comp.get("module", "")
        fn_name     = comp["name"]

        node_id = f"{module_name}::{fn_name}" if module_name else fn_name

        nodes.append({
            "id":        node_id,
            "category":  "function",
            "signature": (comp.get("type_signature", "").split("::", 1)[1].strip()
                          if comp.get("type_signature") else None),
            "location": {
                "start": comp["start_line"],
                "end":   comp["end_line"],
            }
        })

        for call in comp.get("function_calls", []):
            base = call.get("base") or call["name"]

            if call.get("modules"):
                mod = call["modules"][0]
            elif "." in call["name"]:
                mod, base = call["name"].rsplit(".", 1)
            else:
                mod = None

            target_id = f"{mod}::{base}" if mod else base

            edges.append({
                "from":     node_id,
                "to":       target_id,
                "relation": "calls",
            })

        for dep in comp.get("type_dependencies", []):
            edges.append({
                "from":     node_id,
                "to":       dep,
                "relation": "depends_on",
            })

    seen_ids = {n["id"] for n in nodes}
    for e in edges:
        for endpoint in (e["from"], e["to"]):
            if endpoint not in seen_ids:
                nodes.append({
                    "id":       endpoint,
                    "category": "unknown"
                })
                seen_ids.add(endpoint)

    return {
        "nodes": nodes,
        "edges": edges,
    }
