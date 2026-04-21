# codetraverse/adapters/java_adapter.py

import os


def infer_project_root(components):
    paths = [os.path.abspath(comp["module"]) for comp in components if comp.get("module")]
    return os.path.commonpath(paths) if paths else None


def make_node_id(comp):
    module = comp.get("file_path") or comp.get("module") or os.environ.get("CURRENT_FILE", "<unknown>")
    kind = comp.get("kind")
    
    if kind in ("method", "constructor") and comp.get("class") and comp.get("name"):
        return f"{module}::{comp['class']}.{comp['name']}"
    elif kind == "field" and comp.get("class") and comp.get("name"):
        return f"{module}::{comp['class']}.{comp['name']}"
    elif comp.get("name"):
        return f"{module}::{comp['name']}"
    
    return f"{module}::{kind}.{comp.get('start_line')}"


def adapt_java_components(raw_components):
    nodes = []
    edges = []

    if raw_components:
        pr = infer_project_root(raw_components)
        os.environ["ROOT_DIR"] = pr
        os.environ["CURRENT_FILE"] = raw_components[0]["module"]

    project_root = infer_project_root(raw_components)
    existing = set()

    # Build import map
    import_map = {}
    for comp in raw_components:
        if comp["kind"] == "import" and comp.get("name"):
            mod = comp["file_path"]
            import_map[comp["name"]] = comp["name"]

    # Nodes
    for comp in raw_components:
        nid = make_node_id(comp)
        if nid in existing:
            continue
        existing.add(nid)

        node = {
            "id": nid,
            "category": comp["kind"],
            "annotations": comp.get("annotations"),
            "parameters": comp.get("parameters"),
            "returns": comp.get("returns"),
            "type": comp.get("type"),
            "location": {
                "start": comp.get("start_line"),
                "end": comp.get("end_line"),
                "module": comp.get("module")
            },
        }
        
        if comp.get("class"):
            node["class"] = comp["class"]
        
        node = {k: v for k, v in node.items() if v is not None}
        nodes.append(node)

    # Inheritance edges (extends)
    for comp in raw_components:
        if comp["kind"] in ("class", "interface") and comp.get("extends"):
            from_id = make_node_id(comp)
            extends_class = comp["extends"].strip()
            to_id = f"{comp['file_path']}::{extends_class}"
            edges.append({"from": from_id, "to": to_id, "relation": "extends"})

    # Implementation edges (implements)
    for comp in raw_components:
        if comp.get("implements"):
            from_id = make_node_id(comp)
            implements_list = comp["implements"].strip()
            for iface in implements_list.split(","):
                iface = iface.strip()
                if iface:
                    to_id = f"{comp['file_path']}::{iface}"
                    edges.append({"from": from_id, "to": to_id, "relation": "implements"})

    # Method call edges
    for comp in raw_components:
        if comp.get("function_calls"):
            from_id = make_node_id(comp)
            for call in comp["function_calls"]:
                tgt = call.get("resolved_callee")
                if not tgt:
                    continue
                
                parts = tgt.split("::")
                if len(parts) == 2:
                    # Check if imported
                    func_name = parts[1]
                    if import_map.get(func_name):
                        mod = import_map[func_name]
                        path = mod.replace(".", "/") + ".java"
                        tgt = f"{path}::{func_name}"
                
                if from_id != tgt:
                    edges.append({"from": from_id, "to": tgt, "relation": "calls"})

    # Filter empty edges
    edges = [e for e in edges if e["from"] and e["to"]]
    
    return {"nodes": nodes, "edges": edges}
