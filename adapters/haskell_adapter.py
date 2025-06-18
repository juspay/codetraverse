from collections import defaultdict

def adapt_haskell_components(raw_components):
    # First pass: find the module name
    current_module = None
    for comp in raw_components:
        if comp["kind"] == "module_header":
            current_module = comp["name"]
            break
    
    nodes = []
    edges = []
    node_ids = set()

    component_index = {}
    for comp in raw_components:
        if comp["kind"] in ["function", "data_type", "instance"]:
            comp_module = comp.get("module", current_module)
            node_id = f"{comp_module}::{comp['name']}"
            component_index[node_id] = comp

    # Build re-export mapping
    reexport_map = defaultdict(list)
    for comp in raw_components:
        if comp["kind"] == "import" and comp["alias"]:
            key = f"{comp['module']}::{comp['alias']}"
            reexport_map[key].append(comp["module"])

    # Create nodes for all components
    for comp in raw_components:
        # Skip imports and pragmas as standalone nodes
        if comp["kind"] in ["import", "pragma"]:
            continue

        # Handle module header differently
        if comp["kind"] == "module_header":
            # Create proxy nodes for re-exported modules
            for reexported in comp.get("reexported_modules", []):
                proxy_id = f"{comp['name']}::{reexported}"
                nodes.append({
                    "id": proxy_id,
                    "category": "reexport",
                    "name": reexported,
                    "file_path": comp["file_path"],
                    "location": comp.get("location", {})
                })
                node_ids.add(proxy_id)

        # Get module path from component (should be set in extractor)
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
                "file_path": comp["file_path"],
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
                "file_path": comp["file_path"],
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
                "file_path": comp["file_path"],
                "location": {
                    "start": comp["start_line"],
                    "end": comp["end_line"],
                }
            })
        
        node_ids.add(node_id)

    # Create edges based on relationships
    for comp in raw_components:
        if comp["kind"] not in ["function", "data_type", "instance"]:
            continue
        
        # Get module path from component
        comp_module = comp.get("module", current_module)
        comp_name = comp["name"]
        source_id = f"{comp_module}::{comp_name}" if comp_module else comp_name
        if comp["kind"] == "module_header":
            for reexported in comp.get("reexported_modules", []):
                source_id = f"{comp['name']}::{reexported}"
                # Find actual implementations
                for submodule in reexport_map.get(source_id, []):
                    # Create edge to actual module
                    target_id = f"{submodule}::{reexported}"
                    edges.append({
                        "from": source_id,
                        "to": target_id,
                        "relation": "reexports",
                    })

        # Handle function calls
        if comp["kind"] == "function":
            for call in comp.get("function_calls", []):
                # Get target module and base name
                if call.get("modules"):
                    target_module = call["modules"][0]
                    base_name = call["base"]
                elif "." in call["name"]:
                    # Handle qualified names directly in call name
                    target_module, base_name = call["name"].rsplit(".", 1)
                else:
                    # Default to current module
                    target_module = comp_module
                    base_name = call["name"]
                
                target_id = f"{target_module}::{base_name}"
                
                # Check if this is a re-exported module
                if target_id not in component_index:
                    # Try to find actual implementation
                    for actual_module in reexport_map.get(target_id, []):
                        actual_id = f"{actual_module}::{base_name}"
                        if actual_id in component_index:
                            target_id = actual_id
                            break
                
                edges.append({
                    "from": source_id,
                    "to": target_id,
                    "relation": "calls",
                })
        
        # Handle type dependencies
        if comp["kind"] == "function":
            for dep in comp.get("type_dependencies", []):
                if "." in dep:
                    dep_module, dep_name = dep.rsplit(".", 1)
                else:
                    dep_module = comp_module
                    dep_name = dep
                
                target_id = f"{dep_module}::{dep_name}" if dep_module else dep_name
                
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
                        field_module, field_name = type_info["name"].rsplit(".", 1)
                    else:
                        field_module = comp_module
                        field_name = type_info.get("name", "")
                    
                    if not field_name:
                        continue
                    
                    target_id = f"{field_module}::{field_name}" if field_module else field_name
                    
                    edges.append({
                        "from": source_id,
                        "to": target_id,
                        "relation": "contains",
                    })
    
    # Create nodes for any missing dependencies
    for edge in edges:
        for endpoint in (edge["from"], edge["to"]):
            if endpoint not in node_ids:
                # Determine category based on naming convention
                if endpoint.endswith("::") or not endpoint:
                    continue
                    
                # Extract base name
                base_name = endpoint.split("::")[-1] if "::" in endpoint else endpoint
                
                if base_name and base_name[0].isupper():
                    category = "external_type"
                else:
                    category = "external_function"
                
                nodes.append({
                    "id": endpoint,
                    "category": category,
                    "file_path": "external"  # Mark as external
                })
                node_ids.add(endpoint)
    
    print(f"Created {len(nodes)} nodes and {len(edges)} edges")
    return {
        "nodes": nodes,
        "edges": edges,
    }