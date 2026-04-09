from collections import defaultdict


def adapt_java_components(raw_components):
    nodes = []
    edges = []
    id_set = set()
    func_lookup = defaultdict(list)  # function name -> list of full-path IDs

    def signature_for(comp):
        kind = comp.get("kind")
        name = comp.get("name", "")
        
        if kind in ("method", "constructor"):
            params = comp.get("parameters", [])
            param_types = comp.get("parameter_types", {})
            params_sig = ", ".join(
                f"{p} {param_types[p]}" if p in param_types else p
                for p in params
            )
            ret_type = comp.get("return_type", "")
            if kind == "constructor":
                sig = f"{name}({params_sig})"
            else:
                sig = f"{name}({params_sig})"
                if ret_type:
                    sig += f" : {ret_type}"
            return sig
        elif kind == "class":
            extends = comp.get("extends")
            implements = comp.get("implements", [])
            sig = f"class {name}"
            if extends:
                sig += f" extends {extends}"
            if implements:
                sig += f" implements {', '.join(implements)}"
            return sig
        elif kind == "interface":
            extends = comp.get("extends", [])
            sig = f"interface {name}"
            if extends:
                sig += f" extends {', '.join(extends)}"
            return sig
        elif kind == "enum":
            return f"enum {name}"
        else:
            return name or "unknown"

    # --- 1. Build NODES and func_lookup ---
    for comp in raw_components:
        kind = comp.get("kind")
        if kind == "file":
            continue

        node_id = comp.get("complete_function_path")
        if not node_id:
            # fallback: build from file_path + name
            name = comp.get("name")
            fallback_path = comp.get("file_path", "").replace("/", ".").replace("\\", ".")
            node_id = f"{fallback_path}.{name}" if name else None
            if not node_id:
                continue

        # Avoid duplicate IDs
        if node_id in id_set:
            continue
        id_set.add(node_id)

        node = {
            "id": node_id,
            "category": kind,
            "signature": signature_for(comp),
            "location": {
                "start": comp.get("start_line") or (comp.get("location") or {}).get("start"),
                "end": comp.get("end_line") or (comp.get("location") or {}).get("end"),
            }
        }
        nodes.append(node)

        if kind in ("method", "constructor"):
            # Use (name, file_path) as lookup key
            func_lookup[(comp.get("name", ""), comp.get("file_path", ""))].append(node_id)

    # --- 2. Build EDGES using full node IDs only ---
    for comp in raw_components:
        kind = comp.get("kind")
        if kind == "file":
            continue

        from_id = comp.get("complete_function_path")
        if not from_id:
            name = comp.get("name")
            fallback_path = comp.get("file_path", "").replace("/", ".").replace("\\", ".")
            from_id = f"{fallback_path}.{name}" if name else None
            if not from_id:
                continue

        if kind in ("method", "constructor"):
            # Calls: try to match both name+file (strong) or just name (fallback)
            for call in comp.get("function_calls", []):
                to_ids = []
                # Clean the call name (remove "new " prefix, etc.)
                clean_call = call
                if call.startswith("new "):
                    clean_call = call[4:]  # Remove "new " prefix
                
                # Try: calls from the same file
                if (clean_call, comp.get("file_path", "")) in func_lookup:
                    to_ids = func_lookup[(clean_call, comp.get("file_path", ""))]
                elif (clean_call, "") in func_lookup:
                    to_ids = func_lookup[(clean_call, "")]
                else:
                    # fallback: all matches by name across files
                    to_ids = [
                        id for (n, _), ids in func_lookup.items() if n == clean_call for id in ids
                    ]
                for to_id in to_ids:
                    edges.append({"from": from_id, "to": to_id, "relation": "calls"})
            
            # Type dependencies
            for dep in comp.get("type_dependencies", []):
                if dep:
                    edges.append({"from": from_id, "to": dep, "relation": "uses_type"})
            
            # Method to class relationship
            if kind == "method" and comp.get("receiver_type"):
                edges.append({"from": comp["receiver_type"], "to": from_id, "relation": "has_method"})
            elif kind == "constructor":
                receiver = comp.get("receiver_type")
                if receiver:
                    edges.append({"from": receiver, "to": from_id, "relation": "has_constructor"})
        
        elif kind == "class":
            extends = comp.get("extends")
            if extends:
                edges.append({"from": from_id, "to": extends, "relation": "extends"})
            for impl in comp.get("implements", []):
                if impl:
                    edges.append({"from": from_id, "to": impl, "relation": "implements"})
            for field_type in comp.get("field_types", []):
                if field_type:
                    edges.append({"from": from_id, "to": field_type, "relation": "field_type"})
            for m in comp.get("methods", []):
                m_ids = func_lookup.get((m, comp.get("file_path", "")), []) or \
                        [id for (n, _), ids in func_lookup.items() if n == m for id in ids]
                for m_id in m_ids:
                    edges.append({"from": from_id, "to": m_id, "relation": "has_method"})
        
        elif kind == "interface":
            for ext in comp.get("extends", []):
                if ext:
                    edges.append({"from": from_id, "to": ext, "relation": "extends"})
        
        elif kind == "enum":
            for impl in comp.get("implements", []):
                if impl:
                    edges.append({"from": from_id, "to": impl, "relation": "implements"})

    # --- 3. Add nodes for missing edge endpoints ---
    for edge in edges:
        for end in (edge["from"], edge["to"]):
            if end and end not in id_set:
                nodes.append({"id": end, "category": "unknown"})
                id_set.add(end)

    return {"nodes": nodes, "edges": edges}