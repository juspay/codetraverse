from tqdm import tqdm
from collections import defaultdict

def adapt_haskell_components(raw_components, quiet: bool = True):
    nodes = []
    edges = []
    
    current_module_info = next((comp for comp in raw_components if comp.get("kind") == "module_header"), None)
    if not current_module_info:
        print("Warning: No module_header found. Output may be incomplete.")
        return {"nodes": [], "edges": []}
    
    current_module = current_module_info.get("name")

    # --- 1. Node Creation Pass ---
    # Create nodes for all relevant components.
    node_ids = set()
    for comp in raw_components:
        # Skip components that do not become nodes themselves.
        if comp.get("kind") in ["import", "pragma"]:
            continue

        name = comp.get("name")
        if not name:
            continue

        comp_module = comp.get("module", current_module)
        node_id = f"{comp_module}::{name}"

        if node_id in node_ids:
            continue

        node = {
            "id": node_id,
            "category": comp.get("kind"),
            "name": name,
            "file_path": comp.get("file_path", ""),
            "location": {
                "start": comp.get("start_line"),
                "end": comp.get("end_line"),
            }
        }
        
        if comp.get("kind") == "function":
            node["signature"] = comp.get("type_signature")
        
        nodes.append(node)
        node_ids.add(node_id)

    # --- 2. Edge Creation Pass ---
    # Create edges based on dependencies.
    for comp in tqdm(raw_components, total=len(raw_components), desc="Adapting Haskell components"):
        # **FIX**: Only process components that can be a source of edges
        # and are guaranteed to have a "name" key.
        kind = comp.get("kind")
        if kind not in ["module_header", "function", "data_type", "instance"]:
            continue

        comp_module = comp.get("module", current_module)
        source_id = f"{comp_module}::{comp['name']}"

        if kind == "module_header":
            for export_name in comp.get("exports", []):
                target_id = f"{comp['name']}::{export_name}"
                edges.append({"from": source_id, "to": target_id, "relation": "exports"})

        elif kind == "function":
            for call in comp.get("function_calls", []):
                call_base = call.get("base", call.get("name"))
                if not call_base: continue

                target_id = None
                if call.get("type") == "qualified" and call.get("modules"):
                    target_id = f"{call['modules'][0]}::{call_base}"
                else:
                    target_id = f"{comp_module}::{call_base}"
                edges.append({"from": source_id, "to": target_id, "relation": "calls"})

            for dep in comp.get("type_dependencies", []):
                target_id = f"{comp_module}::{dep}"
                if "." in dep:
                    parts = dep.rsplit(".", 1)
                    target_id = f"{parts[0]}::{parts[1]}"
                edges.append({"from": source_id, "to": target_id, "relation": "uses_type"})

        elif kind == "data_type":
            for constructor in comp.get("constructors", []):
                for field in constructor.get("fields", []):
                    type_info = field.get("type_info", {})
                    base_name = type_info.get("base")
                    if not base_name: continue

                    target_id = f"{comp_module}::{base_name}"
                    if type_info.get("modules"):
                        target_id = f"{type_info['modules'][0]}::{base_name}"
                    
                    edges.append({"from": source_id, "to": target_id, "relation": "contains"})

        elif kind == "instance":
             for pattern in comp.get("type_patterns", []):
                 base_name = pattern.get("base", pattern.get("name"))
                 if not base_name: continue
                 
                 target_id = f"{comp_module}::{base_name}"
                 if pattern.get("type") == "qualified" and pattern.get("modules"):
                     target_id = f"{pattern['modules'][0]}::{base_name}"
                 edges.append({"from": source_id, "to": target_id, "relation": "instance_for"})
             
             class_name = comp["name"].split()[0]
             # This assumes the class is in the same module if not qualified, which may need refinement.
             class_id = f"{comp_module}::{class_name}" 
             edges.append({"from": source_id, "to": class_id, "relation": "implements"})

    # --- 3. External Node Creation Pass ---
    # Create placeholder nodes for any dependencies that were not found in the source.
    for edge in edges:
        for endpoint in ("from", "to"):
            endpoint_id = edge[endpoint]
            if endpoint_id not in node_ids:
                if not endpoint_id or "::" not in endpoint_id: continue
                
                name_part = endpoint_id.split("::", 1)[1]
                category = "external_function"
                if name_part and name_part[0].isupper():
                    category = "external_type"
                
                nodes.append({
                    "id": endpoint_id,
                    "category": category,
                    "name": name_part,
                    "file_path": "external",
                })
                node_ids.add(endpoint_id)

    # Remove duplicate edges before returning
    unique_edges = [dict(t) for t in {tuple(sorted(e.items())) for e in edges}]

    return {"nodes": nodes, "edges": unique_edges}