def adapt_rust_components(raw_components):
    nodes = []
    edges = []
    seen_nodes = {}

    def add_node(name, category, extra=None):
        node = {"id": name, "category": category}
        if extra:
            node.update(extra)
        if name not in seen_nodes:
            seen_nodes[name] = node
            nodes.append(node)
        return node

    def get_location_info(comp):
        return {
            "start": comp["span"]["start_line"],
            "end": comp["span"]["end_line"]
        }

    def process_component(comp, parent_path=""):
        comp_name = comp["name"]
        comp_type = comp["type"]
        
        full_name = f"{parent_path}::{comp_name}" if parent_path else comp_name
        
        if comp_type == "function_item":
            process_function(comp, full_name)
        elif comp_type == "struct_item":
            process_struct(comp, full_name)
        elif comp_type == "enum_item":
            process_enum(comp, full_name)
        elif comp_type == "impl_item":
            process_impl(comp, full_name)
        elif comp_type == "trait_item":
            process_trait(comp, full_name)
        elif comp_type == "mod_item":
            process_module(comp, full_name)
        elif comp_type == "use_declaration":
            process_use_declaration(comp, full_name)
        elif comp_type == "const_item":
            process_const(comp, full_name)
        elif comp_type == "static_item":
            process_static(comp, full_name)
        elif comp_type == "type_alias_item":
            process_type_alias(comp, full_name)
        elif comp_type == "type_item":
            process_associated_type(comp, full_name, parent_path)

        for child in comp.get("children", []):
            process_component(child, full_name)

    def process_function(comp, full_name):
        fn_node = add_node(full_name, "function", {
            "signature": [param.get("name", "") for param in comp.get("parameters", [])],
            "return_type": comp.get("return_type"),
            "visibility": comp.get("visibility", "private"),
            "type_parameters": comp.get("type_parameters"),
            "where_clause": comp.get("where_clause"),
            "location": get_location_info(comp)
        })

        for param in comp.get("parameters", []):
            param_name = param.get("name", "")
            param_type = param.get("type", "")
            if param_name and param_name != "self":
                param_node_name = f"{full_name}::{param_name}"
                add_node(param_node_name, "parameter", {
                    "type": param_type,
                    "location": get_location_info(comp)
                })
                edges.append({
                    "from": full_name,
                    "to": param_node_name,
                    "relation": "defines"
                })

        for call in comp.get("function_calls", []):
            call_info = call if isinstance(call, dict) else {"name": call}
            call_name = call_info.get("name", call_info)
            add_node(call_name, "function")
            edges.append({
                "from": full_name,
                "to": call_name,
                "relation": "calls"
            })

        for method_call in comp.get("method_calls", []):
            method_name = method_call.get("method", "")
            receiver = method_call.get("receiver", "")
            if method_name:
                full_method_name = f"{receiver}.{method_name}" if receiver else method_name
                add_node(full_method_name, "method")
                edges.append({
                    "from": full_name,
                    "to": full_method_name,
                    "relation": "calls"
                })

        for macro_call in comp.get("macro_calls", []):
            macro_name = macro_call.get("name", macro_call)
            add_node(macro_name, "macro")
            edges.append({
                "from": full_name,
                "to": macro_name,
                "relation": "invokes"
            })

        for var in comp.get("variables", []):
            var_name = var.get("name", "")
            var_type = var.get("type", "")
            if var_name:
                var_node_name = f"{full_name}::{var_name}"
                add_node(var_node_name, "variable", {
                    "type": var_type,
                    "value": var.get("value"),
                    "location": get_location_info(comp)
                })
                edges.append({
                    "from": full_name,
                    "to": var_node_name,
                    "relation": "defines"
                })

        for type_used in comp.get("types_used", []):
            add_node(type_used, "type")
            edges.append({
                "from": full_name,
                "to": type_used,
                "relation": "uses"
            })

    def process_struct(comp, full_name):
        struct_node = add_node(full_name, "struct", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp)
        })

        for field in comp.get("fields", []):
            field_name = field.get("name", "")
            field_type = field.get("type", "")
            if field_name:
                field_node_name = f"{full_name}::{field_name}"
                add_node(field_node_name, "field", {
                    "type": field_type,
                    "visibility": field.get("visibility", "private"),
                    "location": get_location_info(comp)
                })
                edges.append({
                    "from": full_name,
                    "to": field_node_name,
                    "relation": "has_field"
                })

                if field_type:
                    add_node(field_type, "type")
                    edges.append({
                        "from": full_name,
                        "to": field_type,
                        "relation": "depends_on"
                    })

    def process_enum(comp, full_name):
        enum_node = add_node(full_name, "enum", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp)
        })

        for variant in comp.get("variants", []):
            variant_name = variant.get("name", "")
            if variant_name:
                variant_node_name = f"{full_name}::{variant_name}"
                add_node(variant_node_name, "variant", {
                    "location": get_location_info(comp)
                })
                edges.append({
                    "from": full_name,
                    "to": variant_node_name,
                    "relation": "has_variant"
                })

                for field in variant.get("fields", []):
                    field_name = field.get("name", "")
                    field_type = field.get("type", "")
                    if field_name:
                        field_node_name = f"{variant_node_name}::{field_name}"
                        add_node(field_node_name, "field", {
                            "type": field_type,
                            "location": get_location_info(comp)
                        })
                        edges.append({
                            "from": variant_node_name,
                            "to": field_node_name,
                            "relation": "has_field"
                        })

                        if field_type:
                            add_node(field_type, "type")
                            edges.append({
                                "from": variant_node_name,
                                "to": field_type,
                                "relation": "depends_on"
                            })

    def process_impl(comp, full_name):
        impl_node = add_node(full_name, "impl", {
            "type_parameters": comp.get("type_parameters"),
            "location": get_location_info(comp)
        })

        if " for " in full_name:
            parts = full_name.split(" for ")
            if len(parts) == 2:
                trait_name = parts[0].strip()
                type_name = parts[1].strip()
                
                add_node(trait_name, "trait")
                add_node(type_name, "type")
                
                edges.append({
                    "from": full_name,
                    "to": trait_name,
                    "relation": "implements"
                })
                edges.append({
                    "from": full_name,
                    "to": type_name,
                    "relation": "for_type"
                })
        elif full_name.startswith("impl "):
            type_name = full_name[5:].strip()
            add_node(type_name, "type")
            edges.append({
                "from": full_name,
                "to": type_name,
                "relation": "for_type"
            })

    def process_trait(comp, full_name):
        trait_node = add_node(full_name, "trait", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp)
        })

        for bound in comp.get("trait_bounds", []):
            add_node(bound, "trait")
            edges.append({
                "from": full_name,
                "to": bound,
                "relation": "extends"
            })

    def process_module(comp, full_name):
        """Process module components."""
        mod_node = add_node(full_name, "module", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp)
        })

    def process_use_declaration(comp, full_name):
        """Process use declarations (imports)."""
        use_node = add_node(full_name, "import", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp)
        })

        for import_path in comp.get("imports", []):
            add_node(import_path, "module")
            edges.append({
                "from": full_name,
                "to": import_path,
                "relation": "imports"
            })

    def process_const(comp, full_name):
        const_node = add_node(full_name, "const", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp)
        })

        for type_used in comp.get("types_used", []):
            add_node(type_used, "type")
            edges.append({
                "from": full_name,
                "to": type_used,
                "relation": "uses"
            })

    def process_static(comp, full_name):
        static_node = add_node(full_name, "static", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp)
        })

        for type_used in comp.get("types_used", []):
            add_node(type_used, "type")
            edges.append({
                "from": full_name,
                "to": type_used,
                "relation": "uses"
            })

    def process_type_alias(comp, full_name):
        alias_node = add_node(full_name, "type_alias", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp)
        })

        # Type dependencies
        for type_used in comp.get("types_used", []):
            add_node(type_used, "type")
            edges.append({
                "from": full_name,
                "to": type_used,
                "relation": "aliases"
            })

    def process_associated_type(comp, full_name, parent_path):
        assoc_type_node = add_node(full_name, "associated_type", {
            "location": get_location_info(comp)
        })

        if parent_path:
            edges.append({
                "from": parent_path,
                "to": full_name,
                "relation": "defines"
            })

        for type_used in comp.get("types_used", []):
            add_node(type_used, "type")
            edges.append({
                "from": full_name,
                "to": type_used,
                "relation": "uses"
            })

    for comp in raw_components:
        process_component(comp)

    for comp in raw_components:
        comp_name = comp["name"]
        if comp_name in seen_nodes:
            for lifetime in comp.get("lifetimes", []):
                add_node(lifetime, "lifetime")
                edges.append({
                    "from": comp_name,
                    "to": lifetime,
                    "relation": "uses"
                })

    return {"nodes": nodes, "edges": edges}