from collections import defaultdict

def adapt_go_components(raw_components):
    nodes = []
    edges = []
    id_set = set()
    func_lookup = defaultdict(list)  # function name -> list of full-path IDs

    def signature_for(comp):
        kind = comp.get("kind")
        name = comp.get("name", "")
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
            fallback_path = comp.get("file_path", "").replace("/", "::").replace("\\", "::")
            node_id = f"{fallback_path}::{name}" if name else None
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
            "module": comp.get("module") or comp.get("file_path", ""),  # Add module field for getModuleInfo compatibility
            "location": {
                "start": comp.get("start_line") or (comp.get("location") or {}).get("start"),
                "end": comp.get("end_line") or (comp.get("location") or {}).get("end"),
            }
        }
        nodes.append(node)

        if kind in ("function", "method"):
            func_lookup[(comp.get("name", ""), comp.get("file_path", ""))].append(node_id)

    # --- 1.5. Create simplified alias nodes for compatibility ---
    # Some tools expect nodes with format "package::function" instead of "package/path/file.go::function"
    alias_nodes = []
    alias_edges = []
    for comp in raw_components:
        kind = comp.get("kind")
        if kind not in ("function", "method", "struct", "interface", "type_alias", "constant", "variable"):
            continue
            
        original_id = comp.get("complete_function_path")
        if not original_id or "::" not in original_id:
            continue
            
        # Extract parts: "api/admin/account.go::RegisterAccount" -> ["api/admin/account.go", "RegisterAccount"] 
        parts = original_id.split("::")
        if len(parts) >= 2:
            # Create simplified alias: "api::RegisterAccount" (extract package from file path)
            file_path = parts[0]  # "api/admin/account.go"
            function = parts[1]  # "RegisterAccount" 
            
            # Extract package name from file path: "api/admin/account.go" -> "api"
            if '/' in file_path:
                # Get the first directory component as package name
                package = file_path.split('/')[0]
            else:
                # Single file, use filename without extension as package
                package = file_path.replace('.go', '') if file_path.endswith('.go') else file_path
            
            alias_id = f"{package}::{function}"
            
            # Only create alias if it's different from original and doesn't already exist
            if alias_id != original_id and alias_id not in {node["id"] for node in nodes}:
                alias_node = {
                    "id": alias_id,
                    "category": kind,
                    "signature": signature_for(comp),
                    "module": package,
                    "location": {
                        "start": comp.get("start_line") or (comp.get("location") or {}).get("start"),
                        "end": comp.get("end_line") or (comp.get("location") or {}).get("end"),
                    }
                }
                alias_nodes.append(alias_node)
                alias_edges.append({"from": alias_id, "to": original_id, "relation": "alias_of"})

    # Add alias nodes to main nodes list
    nodes.extend(alias_nodes)

    # --- 2. Build EDGES using full node IDs only ---
    for comp in raw_components:
        kind = comp.get("kind")
        if kind == "file":
            continue

        from_id = comp.get("complete_function_path")
        if not from_id:
            name = comp.get("name")
            fallback_path = comp.get("file_path", "").replace("/", "::").replace("\\", "::")
            from_id = f"{fallback_path}::{name}" if name else None
            if not from_id:
                continue

        if kind in ("function", "method"):
            # Calls: try to match both name+file (strong) or just name (fallback)
            for call in comp.get("function_calls", []):
                # Prefer full path if available, fallback to all nodes with that name
                to_ids = []
                # Try: calls from the same file
                if (call, comp.get("file_path", "")) in func_lookup:
                    to_ids = func_lookup[(call, comp.get("file_path", ""))]
                elif (call, "") in func_lookup:
                    to_ids = func_lookup[(call, "")]
                else:
                    # fallback: all matches by name across files
                    to_ids = [
                        id for (n, _), ids in func_lookup.items() if n == call for id in ids
                    ]
                for to_id in to_ids:
                    edges.append({"from": from_id, "to": to_id, "relation": "calls"})
            for dep in comp.get("type_dependencies", []):
                if dep:
                    edges.append({"from": from_id, "to": dep, "relation": "uses_type"})
            if kind == "method" and comp.get("receiver_type"):
                edges.append({"from": comp["receiver_type"], "to": from_id, "relation": "has_method"})
        elif kind == "struct":
            for field_type in comp.get("field_types", []):
                if field_type:
                    edges.append({"from": from_id, "to": field_type, "relation": "field_type"})
            for m in comp.get("methods", []):
                m_ids = func_lookup.get((m, comp.get("file_path", "")), []) or \
                        [id for (n, _), ids in func_lookup.items() if n == m for id in ids]
                for m_id in m_ids:
                    edges.append({"from": from_id, "to": m_id, "relation": "has_method"})
        elif kind == "interface":
            for dep in comp.get("type_dependencies", []):
                if dep:
                    edges.append({"from": from_id, "to": dep, "relation": "interface_dep"})
        elif kind == "type_alias":
            aliased = comp.get("aliased_type")
            if aliased:
                edges.append({"from": from_id, "to": aliased, "relation": "type_alias"})
        elif kind in ("constant", "variable"):
            typ = comp.get("type")
            if typ:
                edges.append({"from": from_id, "to": typ, "relation": "var_type"})

    # --- 3. Add nodes for missing edge endpoints ---
    for edge in edges:
        for end in (edge["from"], edge["to"]):
            if end and end not in id_set:
                nodes.append({
                    "id": end, 
                    "category": "unknown",
                    "module": end.split("::")[0] if "::" in end else "unknown"  # Add module field for getModuleInfo compatibility
                })
                id_set.add(end)

    # --- 4. Add alias edges ---
    edges.extend(alias_edges)

    return {"nodes": nodes, "edges": edges}
