from tqdm import tqdm

def adapt_haskell_components(raw_components, quiet: bool = True):
    # First pass: find the module name
    current_module = None
    for comp in raw_components:
        if comp["kind"] == "module_header":
            current_module = comp["name"]
            break
    
    nodes = []
    edges = []
    node_ids = set()

    # Build index of all components by their module::name ID
    component_index = {}
    for comp in raw_components:
        if comp["kind"] in ["function", "data_type", "instance"]:
            comp_module = comp.get("module", current_module)
            node_id = f"{comp_module}::{comp['name']}"
            component_index[node_id] = comp

    # Build re-export mapping: {reexport_alias_id: actual_module}
    reexport_map = {}
    for comp in raw_components:
        if comp["kind"] == "import" and comp.get("alias"):
            alias = comp["alias"]
            actual_module = comp["module"]
            reexport_id = f"{current_module}::{alias}"
            reexport_map[reexport_id] = actual_module

    # Create nodes for all components
    for comp in raw_components:
        # Skip imports and pragmas as standalone nodes
        if comp["kind"] in ["import", "pragma"]:
            continue

        # Handle module header - create nodes for re-exported modules
        if comp["kind"] == "module_header":
            for export in comp.get("exports", []):
                # Create node for each export (including X)
                node_id = f"{comp['name']}::{export}"
                nodes.append({
                    "id": node_id,
                    "category": "module_export",
                    "name": export,
                    "file_path": comp.get("file_path", ""),
                    "location": {
                        "start": comp["start_line"],
                        "end": comp["end_line"],
                    }
                })
                node_ids.add(node_id)
            continue

        # Get module path from component
        comp_module = comp.get("module", current_module)
        comp_name = comp["name"]
        
        # Generate node ID: module_path::component_name
        node_id = f"{comp_module}::{comp_name}" if comp_module else comp_name
        
        # Create node based on component type
        if comp["kind"] == "function":
            nodes.append({
                "id": node_id,
                "category": "function",
                "name": comp_name,
                "file_path": comp.get("file_path", ""),
                "signature": comp.get("type_signature"),
                "location": {
                    "start": comp["start_line"],
                    "end": comp["end_line"],
                }
            })
        elif comp["kind"] == "data_type":
            nodes.append({
                "id": node_id,
                "category": "data_type",
                "name": comp_name,
                "file_path": comp.get("file_path", ""),
                "location": {
                    "start": comp["start_line"],
                    "end": comp["end_line"],
                }
            })
        elif comp["kind"] == "instance":
            nodes.append({
                "id": node_id,
                "category": "instance",
                "name": comp_name,
                "file_path": comp.get("file_path", ""),
                "location": {
                    "start": comp["start_line"],
                    "end": comp["end_line"],
                }
            })
        
        node_ids.add(node_id)

    # Create proxy nodes for re-exported functions
    for reexport_id, actual_module in reexport_map.items():
        # Find all components in the actual module
        for comp_id, comp in component_index.items():
            if comp.get("module") == actual_module:
                # Create proxy node: reexporting_module::function_name
                base_name = comp["name"]
                proxy_id = f"{reexport_id.split('::')[0]}::{base_name}"
                
                if proxy_id not in node_ids:
                    nodes.append({
                        "id": proxy_id,
                        "category": "reexport",
                        "name": base_name,
                        "file_path": comp.get("file_path", ""),
                        "location": {}
                    })
                    node_ids.add(proxy_id)
                    
                    # Connect proxy to actual implementation
                    edges.append({
                        "from": proxy_id,
                        "to": comp_id,
                        "relation": "implements",
                    })

    # Create edges for module re-exports (X -> actual functions)
    for comp in raw_components:
        if comp["kind"] == "import" and comp.get("alias"):
            alias = comp["alias"]
            actual_module = comp["module"]
            
            # Create edge from module's alias export to the proxy nodes
            alias_id = f"{current_module}::{alias}"
            
            # Find all proxy nodes for this alias
            for node in nodes:
                if node["id"].startswith(f"{alias_id.split('::')[0]}::") and node["category"] == "reexport":
                    edges.append({
                        "from": alias_id,
                        "to": node["id"],
                        "relation": "exports",
                    })

    # Create edges based on function calls and dependencies
    for comp in tqdm(raw_components, total=len(raw_components), desc="Adapting Haskell components"):
        if comp["kind"] not in ["function", "data_type", "instance"]:
            continue
        
        # Get module path from component
        comp_module = comp.get("module", current_module)
        comp_name = comp["name"]
        source_id = f"{comp_module}::{comp_name}" if comp_module else comp_name
        
        # Handle function calls
        if comp["kind"] == "function":
            for call in comp.get("function_calls", []):
                target_id = None
                
                # Determine target based on call structure
                if call.get("type") == "qualified" and call.get("modules"):
                    target_module = call["modules"][0]
                    base_name = call["base"]
                    target_id = f"{target_module}::{base_name}"
                elif "." in call["name"]:
                    # Handle qualified names
                    parts = call["name"].split(".")
                    if len(parts) >= 2:
                        module_part = ".".join(parts[:-1])
                        base_name = parts[-1]
                        target_id = f"{module_part}::{base_name}"
                else:
                    # Unqualified call - assume current module
                    base_name = call["name"]
                    target_id = f"{comp_module}::{base_name}"
                
                if target_id and source_id in node_ids:
                    # Check if we need to resolve through a proxy
                    resolved_target = target_id
                    if target_id not in node_ids:
                        # Try to find proxy node
                        for node in nodes:
                            if (node["id"] == target_id or 
                               (node["category"] == "reexport" and 
                                node["id"].endswith(f"::{base_name}"))):
                                resolved_target = node["id"]
                                break
                    
                    edges.append({
                        "from": source_id,
                        "to": resolved_target,
                        "relation": "calls",
                    })
        
        # Handle type dependencies
        if comp["kind"] == "function":
            for dep in comp.get("type_dependencies", []):
                if "." in dep:
                    dep_parts = dep.split(".")
                    dep_module = ".".join(dep_parts[:-1])
                    dep_name = dep_parts[-1]
                else:
                    dep_module = comp_module
                    dep_name = dep
                
                target_id = f"{dep_module}::{dep_name}" if dep_module else dep_name
                
                if source_id in node_ids:
                    edges.append({
                        "from": source_id,
                        "to": target_id,
                        "relation": "depends_on",
                    })
        
        # Handle data type fields
        if comp["kind"] == "data_type":
            for constructor in comp.get("constructors", []):
                for field in constructor.get("fields", []):
                    type_info = field.get("type_info", {})
                    if type_info.get("modules"):
                        field_module = type_info["modules"][0]
                        field_name = type_info["base"]
                    elif "." in type_info.get("name", ""):
                        field_parts = type_info["name"].split(".")
                        field_module = ".".join(field_parts[:-1])
                        field_name = field_parts[-1]
                    else:
                        field_module = comp_module
                        field_name = type_info.get("name", "")
                    
                    if not field_name:
                        continue
                    
                    target_id = f"{field_module}::{field_name}" if field_module else field_name
                    
                    if source_id in node_ids:
                        edges.append({
                            "from": source_id,
                            "to": target_id,
                            "relation": "contains",
                        })
    
    # Create nodes for any missing dependencies
    for edge in edges:
        for endpoint in (edge["from"], edge["to"]):
            if endpoint not in node_ids:
                # Skip empty or malformed IDs
                if not endpoint or endpoint.endswith("::") or "::" not in endpoint:
                    continue
                    
                # Extract base name
                base_name = endpoint.split("::")[-1]
                
                if base_name and base_name[0].isupper():
                    category = "external_type"
                else:
                    category = "external_function"
                
                nodes.append({
                    "id": endpoint,
                    "category": category,
                    "name": base_name,
                    "file_path": "external"
                })
                node_ids.add(endpoint)
    if not quiet:
        print(f"Created {len(nodes)} nodes and {len(edges)} edges")
    return {
        "nodes": nodes,
        "edges": edges,
    }