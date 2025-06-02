def adapt_rescript_components(raw_components):
    nodes = []
    edges = []

    def extract_component_name(comp):
        """Helper to extract component name, handling different structures"""
        name = comp.get("name")
        if not name and comp.get("kind") == "jsx":
            name = comp.get("tag_name", "UnknownJSX")
        return name or "Unknown"

    def process_component_recursively(comp, parent_name=None):
        """Recursively process components and their children"""
        kind = comp.get("kind")
        name = extract_component_name(comp)
        
        node = {
            "id": name,
            "category": kind,
            "start_line": comp.get("start_line"),
            "end_line": comp.get("end_line"),
            "signature": comp.get("type_annotation") or comp.get("subkind") or comp.get("type"),
        }

        if kind in ("module", "type"):
            node["snippet_length"] = len(comp.get("code", ""))

        if kind in ("external", "variable", "function"):
            node["raw_code"] = comp.get("code")

        if kind == "function":
            params = comp.get("parameters", [])
            if params:
                node["parameters"] = params
            return_type = comp.get("return_type_annotation")
            if return_type:
                node["return_type"] = return_type

        nodes.append(node)

        if parent_name:
            edges.append({
                "from": parent_name,
                "to": name,
                "relation": "contains"
            })

        function_calls = comp.get("function_calls", [])
        for fn_call in function_calls:
            if isinstance(fn_call, dict):
                target = fn_call.get("name", str(fn_call))
            else:
                target = str(fn_call)
            
            if target and target != name:
                edges.append({
                    "from": name,
                    "to": target,
                    "relation": "calls"
                })

        local_vars = comp.get("local_variables", [])
        for local_var in local_vars:
            if isinstance(local_var, dict):
                local_name = extract_component_name(local_var)
                edges.append({
                    "from": name,
                    "to": local_name,
                    "relation": "defines"
                })
                process_component_recursively(local_var, name)

        jsx_elements = comp.get("jsx_elements", [])
        for jsx_elem in jsx_elements:
            if isinstance(jsx_elem, dict):
                jsx_name = extract_component_name(jsx_elem)
                edges.append({
                    "from": name,
                    "to": jsx_name,
                    "relation": "renders"
                })
                process_component_recursively(jsx_elem, name)

        if kind == "module":
            elements = comp.get("elements", [])
            for element in elements:
                if isinstance(element, dict):
                    process_component_recursively(element, name)

        if kind == "jsx":
            children_jsx = comp.get("children_jsx", [])
            for child_jsx in children_jsx:
                if isinstance(child_jsx, dict):
                    process_component_recursively(child_jsx, name)

        if kind == "type":
            variants = comp.get("variants", [])
            for variant in variants:
                if isinstance(variant, dict):
                    variant_name = variant.get("name")
                    if variant_name:
                        edges.append({
                            "from": name,
                            "to": variant_name,
                            "relation": "defines_variant"
                        })

    for comp in raw_components:
        process_component_recursively(comp)

    seen_nodes = {n["id"] for n in nodes}
    for edge in edges:
        for endpoint in (edge["from"], edge["to"]):
            if endpoint not in seen_nodes:
                nodes.append({
                    "id": endpoint,
                    "category": "external_reference"
                })
                seen_nodes.add(endpoint)

    for comp in raw_components:
        comp_name = extract_component_name(comp)
        import_map = comp.get("import_map", {})
        for module_name, import_list in import_map.items():
            for import_info in import_list:
                import_type = import_info.get("type", "unknown")
                edges.append({
                    "from": comp_name,
                    "to": module_name,
                    "relation": f"imports_{import_type}"
                })

    print(f"Created {len(nodes)} nodes and {len(edges)} edges")
    print(f"Sample edges: {edges[:5] if edges else 'No edges created'}")
    
    return {"nodes": nodes, "edges": edges}