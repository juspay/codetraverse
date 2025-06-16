def adapt_go_components(raw_components):
    nodes = []
    edges = []

    def signature_for(comp):
        kind = comp.get("kind")
        name = comp.get("name")
        if kind in ("function", "method"):
            params = comp.get("parameters", [])
            param_types = comp.get("parameter_types", {})
            params_sig = ", ".join(
                f"{p} {param_types[p]}" if p in param_types else p
                for p in params
            )
            ret_type = comp.get("return_type", "")
            sig = f"func {name}({params_sig})"
            if ret_type:
                sig += f" {ret_type}"
            if kind == "method" and comp.get("receiver_type"):
                sig = f"func ({comp['receiver_type']}) " + sig
            return sig
        elif kind == "struct":
            return f"struct {name}"
        elif kind == "interface":
            return f"interface {name}"
        elif kind == "type_alias":
            return f"type {name} = {comp.get('aliased_type')}"
        elif kind == "constant":
            return f"const {name} {comp.get('type', '')} = {comp.get('value', '')}"
        elif kind == "variable":
            return f"var {name} {comp.get('type', '')} = {comp.get('value', '')}"
        else:
            return name

    id_set = set()
    # Build a lookup table from name to complete_function_path
    func_lookup = {}
    for comp in raw_components:
        if comp.get("kind") in ("function", "method"):
            func_lookup[comp["name"]] = comp.get("complete_function_path", comp["name"])
        # Optionally, index all by (package, name) or by more context if you want!

    for comp in raw_components:
        kind = comp.get("kind")
        if kind == "file":
            continue
        # Use complete_function_path as unique id if present
        node_id = comp.get("complete_function_path") or comp.get("name")
        if not node_id or not kind:
            continue
        node = {
            "id": node_id,
            "category": kind,
            "signature": signature_for(comp),
            "location": {
                "start": comp.get("start_line") or comp.get("location", {}).get("start"),
                "end": comp.get("end_line") or comp.get("location", {}).get("end"),
            }
        }
        nodes.append(node)
        id_set.add(node_id)

    # Edges
    for comp in raw_components:
        kind = comp.get("kind")
        if kind == "file":
            continue
        from_id = comp.get("complete_function_path") or comp.get("name")
        if not from_id:
            continue
        # Function/method calls
        if kind in ("function", "method"):
            for call in comp.get("function_calls", []):
                # Try to find the correct unique id for the call target
                to_id = func_lookup.get(call, call)
                if to_id:
                    edges.append({"from": from_id, "to": to_id, "relation": "calls"})
            # Type dependencies
            for dep in comp.get("type_dependencies", []):
                if dep:
                    edges.append({"from": from_id, "to": dep, "relation": "uses_type"})
            # Method belonging to struct
            if kind == "method" and comp.get("receiver_type"):
                edges.append({"from": comp["receiver_type"], "to": from_id, "relation": "has_method"})
        # Struct field type deps
        if kind == "struct":
            for field_type in comp.get("field_types", []):
                if field_type:
                    edges.append({"from": from_id, "to": field_type, "relation": "field_type"})
            for m in comp.get("methods", []):
                # Try to find the unique id for the method
                m_id = func_lookup.get(m, m)
                edges.append({"from": from_id, "to": m_id, "relation": "has_method"})
        # Interface type deps
        if kind == "interface":
            for dep in comp.get("type_dependencies", []):
                if dep:
                    edges.append({"from": from_id, "to": dep, "relation": "interface_dep"})
        # Type alias
        if kind == "type_alias":
            aliased = comp.get("aliased_type")
            if aliased:
                edges.append({"from": from_id, "to": aliased, "relation": "type_alias"})
        # Variable/constant type
        if kind in ("constant", "variable"):
            typ = comp.get("type")
            if typ:
                edges.append({"from": from_id, "to": typ, "relation": "var_type"})

    # Ensure all edge endpoints are in the node list
    for e in edges:
        for end in (e["from"], e["to"]):
            if end and end not in id_set:
                nodes.append({"id": end, "category": "unknown"})
                id_set.add(end)

    return {"nodes": nodes, "edges": edges}
