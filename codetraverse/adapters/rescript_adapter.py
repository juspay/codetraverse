def extract_id(comp):
    """
    Build a stable ID: "<module>::<name_or_tag>". 
    If comp["module_name"] is present, use it; otherwise fall back to comp["file_name"].
    The raw “name” may sometimes be missing (e.g. for JSX), so we also fall back to comp["tag_name"].
    """
    module_part = comp.get("module_name") or comp.get("file_name") or "<anonymous>"
    name_part = comp.get("name") or comp.get("tag_name") or "<unknown>"
    return f"{module_part}::{name_part}"


def adapt_rescript_components(raw_components):
    """
    A lightweight adapter that only registers top‐level functions, variables, and modules,
    and creates “calls” edges between them.  We skip nested local_variables, literals, jsx, etc.
    """
    nodes = []
    edges = []

    # 1) Precompute all fully‐qualified IDs
    fq_ids = []
    comp_by_fq = {}
    for comp in raw_components:
        fq = extract_id(comp)
        fq_ids.append(fq)
        comp_by_fq[fq] = comp

    # 2) Build a set of module‐names and a map from module_name to its FQ IDs
    all_module_names = set()
    module_to_fq_map = {}
    for fq_id_val in fq_ids:
        module_name_part = fq_id_val.split("::", 1)[0]
        all_module_names.add(module_name_part)
        if module_name_part not in module_to_fq_map:
            module_to_fq_map[module_name_part] = []
        module_to_fq_map[module_name_part].append(fq_id_val)
    
    for comp in raw_components:
        kind = comp.get("kind")
        if kind not in ("function", "variable", "module"):
            continue

        fq = extract_id(comp)
        nodes.append({
            "id":       fq,
            "category": kind,
            "start":    comp.get("start_line", 0),
            "end":      comp.get("end_line", 0)
        })

        for raw_call in comp.get("function_calls", []):
            if isinstance(raw_call, dict):
                target_bare = raw_call.get("name") or raw_call.get("tag_name") or ""
            else:
                target_bare = str(raw_call)
            target_bare = target_bare.strip()
            if not target_bare:
                continue

            if target_bare in all_module_names:

                for candidate_fq in module_to_fq_map.get(target_bare, []):
                    edges.append({
                        "from":     fq,
                        "to":       candidate_fq,
                        "relation": "calls"
                    })
            else:
                edges.append({
                    "from":     fq,
                    "to":       target_bare,
                    "relation": "calls"
                })

    seen = {n["id"] for n in nodes}
    for e in edges:
        for endpoint in (e["from"], e["to"]):
            if endpoint not in seen:
                # Decide a category for stubs
                cat = "external_reference"
                if "." in endpoint:
                    cat = "module_function"
                elif e["relation"] == "calls":
                    cat = "external_function"
                nodes.append({"id": endpoint, "category": cat})
                seen.add(endpoint)

    # 5) “imports_*” edges for every comp’s import_map
    for comp in raw_components:
        fq = extract_id(comp)
        for mod_name, import_list in comp.get("import_map", {}).items():
            for import_info in import_list:
                import_type = import_info.get("type", "unknown")
                edges.append({
                    "from":     fq,
                    "to":       mod_name,
                    "relation": f"imports_{import_type}"
                })

    print(f"Created {len(nodes)} nodes and {len(edges)} edges (functions/variables/modules only)")
    fn_edges = [e for e in edges if e["relation"] == "calls"]
    print(f"Function‐call edges: {len(fn_edges)}")
    return {"nodes": nodes, "edges": edges}