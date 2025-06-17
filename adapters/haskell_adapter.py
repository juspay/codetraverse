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

    # Create nodes for all components
    for comp in raw_components:
        if comp["kind"] == "module_header":
            node_id = comp["name"]
            nodes.append({
                "id": node_id,
                "category": "module",
                "name": comp["name"],
                "location": {
                    "start": comp["start_line"],
                    "end": comp["end_line"],
                }
            })
            node_ids.add(node_id)
            continue

        # Skip imports and pragmas as standalone nodes
        if comp["kind"] in ["import", "pragma"]:
            continue

        # Generate node ID: module::component_name
        comp_name = comp["name"]
        node_id = f"{current_module}::{comp_name}" if current_module else comp_name
        
        # Create node based on component type
        if comp["kind"] == "function":
            nodes.append({
                "id": node_id,
                "category": "function",
                "name": comp_name,
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
        
        comp_name = comp["name"]
        source_id = f"{current_module}::{comp_name}" if current_module else comp_name
        
        # Handle function calls
        if comp["kind"] == "function":
            for call in comp.get("function_calls", []):
                # Get target module and base name
                if call.get("modules"):
                    target_module = call["modules"][0]
                    base_name = call["base"]
                elif "." in call["name"]:
                    target_module, base_name = call["name"].rsplit(".", 1)
                else:
                    target_module = current_module
                    base_name = call["name"]
                
                target_id = f"{target_module}::{base_name}" if target_module else base_name
                
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
                    dep_module = current_module
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
                        field_module = current_module
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
                    
                if endpoint.split("::")[-1][0].isupper():
                    category = "external_type"
                else:
                    category = "external_function"
                
                nodes.append({
                    "id": endpoint,
                    "category": category
                })
                node_ids.add(endpoint)
    
    print(f"Created {len(nodes)} nodes and {len(edges)} edges")
    return {
        "nodes": nodes,
        "edges": edges,
    }