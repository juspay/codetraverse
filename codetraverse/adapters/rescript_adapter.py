def extract_id(comp):
    """
    Build a stable ID: "<file_path>::<name_or_tag>".
    The module part is intentionally omitted to simplify matching for nested components.
    """
    file_path = comp.get("relative_path", "")
    name_part = comp.get("name") or comp.get("tag_name") or "<unknown>"
    return f"{file_path}::{name_part}"

def adapt_rescript_components(raw_components):
    """
    A lightweight adapter that registers functions, variables, modules, and externals,
    and creates “calls” edges between them. It processes nested components.
    """
    nodes = []
    edges = []
    created_node = set()

    all_components = []
    def flatten_components(comps, parent_comp=None):
        for comp in comps:
            if parent_comp:
                if "relative_path" not in comp:
                    comp["relative_path"] = parent_comp.get("relative_path")
                if "file_path" not in comp:
                    comp["file_path"] = parent_comp.get("file_path")
            all_components.append(comp)
            if "local_variables" in comp:
                flatten_components(comp.get("local_variables", []), comp)
            if "elements" in comp:
                flatten_components(comp.get("elements", []), comp)

    flatten_components(raw_components)

    for comp in all_components:
        kind = comp.get("kind")
        file_path = comp.get("file_path")

        if kind not in ("function", "module", "type", "external", "jsx") or (file_path and "/node_modules/" in file_path):
            continue
        
        if comp.get("name") == "make" and kind == "module":
            continue
        
        fq = extract_id(comp) 
        if fq in created_node:
            continue
        created_node.add(fq)   

        nodes.append({
            "id": fq,
            "category": kind,
            "start": comp.get("start_line", 0),
            "end": comp.get("end_line", 0),
            "code": comp.get("code", ""),
            "function_calls": comp.get("function_calls", []),
            "file_path": comp.get("file_path", "")
        })

    for comp in all_components:
        kind = comp.get("kind")
        file_path = comp.get("file_path")
        if kind not in ("function", "module", "jsx", "type","external")  or (file_path and "/node_modules/" in file_path):
            continue 
        
        if comp.get("name") == "make" and  kind == "module":
            continue

        fq = extract_id(comp)

        for raw_call in comp.get("function_calls", []):
            if isinstance(raw_call, dict):
                target_bare = raw_call.get("name") or raw_call.get("tag_name") or ""
            else:
                target_bare = str(raw_call)
            target_bare = target_bare.strip()
            if not target_bare:
                continue 

            #components that was not inside the curr file
            if target_bare + "::make" in created_node: 
                edges.append({
                    "from":     fq,
                    "to":       target_bare + "::make",
                    "relation": "calls"
                })
            
            #functions/externals that were inside the curr file 
            target_fq = comp.get("relative_path", "") + "::" + target_bare
            if target_fq in created_node:
                edges.append({
                    "from":     fq,
                    "to":       target_fq,
                    "relation": "calls"
                })
            
            #components that was inside the curr file 
            target_fq_make = comp.get("relative_path", "") + "::" + target_bare + "::make"
            if target_fq_make in created_node:
                edges.append({
                    "from":     fq,
                    "to":       target_fq_make,
                    "relation": "calls"
                })

    return {"nodes": nodes, "edges": edges}
