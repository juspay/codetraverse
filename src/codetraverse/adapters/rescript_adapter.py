import json
from tqdm import tqdm

def extract_id(comp):
    """
    Build a stable ID: "<module>::<name_or_tag>". 
    If comp["module_name"] is present, use it; otherwise fall back to comp["file_name"].
    The raw “name” may sometimes be missing (e.g. for JSX), so we also fall back to comp["tag_name"].
    """

    file_name = comp.get("file_name") 
    module_part = comp.get("module_name")
    name_part = comp.get("name") or comp.get("tag_name") or "<unknown>"
    name_part = name_part if module_part != name_part else "make"

    return f"{file_name}.{module_part}::{name_part}" if module_part else f"{file_name}::{name_part}"

def adapt_rescript_components(raw_components):
    """
    A lightweight adapter that only registers top‐level functions, variables, and modules,
    and creates “calls” edges between them.  We skip nested local_variables, literals, jsx, etc.
    """
    nodes = []
    edges = []
    # module_to_fq_map = {}
    # for comp in raw_components:
    #     if comp.get("kind") == "function": 
    #         funprefix = comp["file_name"] + "." + comp["module_name"] if comp.get("module_name") else comp["file_name"] 
    #         modprefix = comp["module_name"] if comp.get("module_name") else comp["file_name"]
    #         if modprefix + "::make" not in module_to_fq_map:
    #             module_to_fq_map[modprefix + "::make"] =[]
    #         module_to_fq_map[modprefix + "::make"].append(funprefix + "::" + comp["name"])

    # 3) Now iterate once over raw_components (with a progress bar)
    created_node = set()
    for comp in tqdm(raw_components, desc="Adapting ReScript components"):
        kind = comp.get("kind")
        # Only register top‐level functions, variables, modules
        if kind not in ("function", "module"):
            continue 
        
        if comp.get("name") == "make" and kind == "module":
            continue
        
        fq = extract_id(comp) 
        created_node.add(fq)   
        # 3a) Emit a single node‐entry
        nodes.append({
            "id": fq,
            "category": kind,
            "start": comp.get("start_line", 0),
            "end": comp.get("end_line", 0),
            "code": comp.get("code", ""),
            "function_calls": comp.get("function_calls", []),
            "file_path": comp.get("file_path", "")
        })

    for comp in tqdm(raw_components, desc="Connecting components"):

        kind = comp.get("kind")
        # Only register top‐level functions, variables, modules
        if kind not in ("function", "module"):
            continue 
        
        if comp.get("name") == "make" and  kind == "module":
            continue

        # 3b) For each bare function‐call, attempt to fan-out to any FQ whose module matches
        for raw_call in comp.get("function_calls", []):
            # raw_call may be a dict or string; extract a bare name
            if isinstance(raw_call, dict):
                print("i saw a dict:.......",comp["name"], comp["kind"], comp["file_path"])
                target_bare = raw_call.get("name") or raw_call.get("tag_name") or ""
            else:
                target_bare = str(raw_call)
            target_bare = target_bare.strip()
            if not target_bare:
                continue 

            fq = extract_id(comp)    
            
            if target_bare + "::make" in created_node: 
                edges.append({
                    "from":     fq,
                    "to":       target_bare + "::make",
                    "relation": "calls"
                })
            
            if comp["file_name"] + "::" + target_bare in created_node:
                edges.append({
                    "from":     fq,
                    "to":      comp["file_name"] + "::" + target_bare,
                    "relation": "calls"
                })

    print(f"Created {len(created_node)} nodes and {len(edges)} edges (functions/variables/modules only)")
    fn_edges = [e for e in edges if e["relation"] == "calls"]
    print(f"Function‐call edges: {len(fn_edges)}")
    return {"nodes": nodes, "edges": edges}
