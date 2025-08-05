def extract_id(comp):
    """
    Build a stable ID: "<module>::<name_or_tag>". 
    If comp["module_name"] is present, use it; otherwise fall back to comp["file_name"].
    The raw “name” may sometimes be missing (e.g. for JSX), so we also fall back to comp["tag_name"].
    """
    file_path = comp.get("relative_path", "")
    module_part = comp.get("module_name")
    name_part = comp.get("name") or comp.get("tag_name") or "<unknown>"
    name_part = name_part if module_part != name_part else "make"

    return f"{file_path}::{module_part}::{name_part}" if module_part else f"{file_path}::{name_part}"

def adapt_rescript_components(raw_components):
    """
    A lightweight adapter that only registers top‐level functions, variables, and modules,
    and creates “calls” edges between them.  We skip nested local_variables, literals, jsx, etc.
    """
    nodes = []
    edges = []
    created_node = set()
    for comp in raw_components:
        kind = comp.get("kind")
        file_path = comp.get("file_path")

        if kind not in ("function", "module") or "/node_modules/" in file_path:
            continue 
        
        if comp.get("name") == "make" and kind == "module":
            continue
        
        fq = extract_id(comp) 
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

    for comp in raw_components:

        kind = comp.get("kind")
        file_path = comp.get("file_path")
        if kind not in ("function", "module")  or "/node_modules/" in file_path:
            continue 
        
        if comp.get("name") == "make" and  kind == "module":
            continue

        for raw_call in comp.get("function_calls", []):
            if isinstance(raw_call, dict):
                target_bare = raw_call.get("name") or raw_call.get("tag_name") or ""
            else:
                target_bare = str(raw_call)
            target_bare = target_bare.strip()
            if not target_bare:
                continue 

            fq = extract_id(comp)    
            #components that was not inside the curr file
            if target_bare + "::make" in created_node: 
                edges.append({
                    "from":     fq,
                    "to":       target_bare + "::make",
                    "relation": "calls"
                })
            
            #functions that was inside the curr file 
            if comp["relative_path"] + "::" + target_bare in created_node:
                edges.append({
                    "from":     fq,
                    "to":       comp["relative_path"] + "::" + target_bare,
                    "relation": "calls"
                })
            
            #components that was inside the curr file 
            if comp["relative_path"] + "::" + target_bare + "::make" in created_node:
                edges.append({
                    "from":     fq,
                    "to":       comp["relative_path"] + "::" + target_bare + "::make",
                    "relation": "calls"
                })

    return {"nodes": nodes, "edges": edges}