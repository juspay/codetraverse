def adapt_rust_components(raw_components, file_path=None, crate_name="crate"):
    """
    Adapt Rust components to graph format using full module paths as unique identifiers.
    
    Args:
        raw_components: List of parsed Rust components
        file_path: Optional file path (e.g., "src/utils.rs") to determine module path
        crate_name: Name of the crate (defaults to "crate")
    """
    nodes = []
    edges = []
    seen_nodes = {}
    
    # Determine the module path from file path
    def get_module_path_from_file(file_path, crate_name):
        if not file_path:
            return crate_name
        
        # Convert file path to module path
        # src/utils.rs -> crate::utils
        # src/models/user.rs -> crate::models::user
        # lib.rs or main.rs -> crate
        
        import os
        file_path = file_path.replace("\\", "/")  # Normalize path separators
        
        # Remove common prefixes
        if file_path.startswith("src/"):
            file_path = file_path[4:]
        elif file_path.startswith("./src/"):
            file_path = file_path[6:]
        
        # Handle special cases
        if file_path in ["main.rs", "lib.rs"]:
            return crate_name
        
        # Convert to module path
        if file_path.endswith(".rs"):
            file_path = file_path[:-3]
        
        # Replace path separators with module separators
        module_parts = file_path.split("/")
        if module_parts:
            return f"{crate_name}::{('::'.join(module_parts))}"
        
        return crate_name

    # Get the base module path for this file
    base_module_path = get_module_path_from_file(file_path, crate_name)

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
            "start": comp.get("span", {}).get("start_line", 0),
            "end": comp.get("span", {}).get("end_line", 0),
            "file": file_path
        }

    def build_full_path(parent_path, comp_name):
        """Build full module path for a component"""
        if not parent_path:
            return f"{base_module_path}::{comp_name}"
        return f"{parent_path}::{comp_name}"

    def normalize_external_reference(ref_name, current_context):
        """
        Normalize external references to use full paths where possible.
        For now, we'll prefix unqualified names with the current context.
        """
        if "::" in ref_name:
            # Already qualified
            return ref_name
        
        # Check if it's a standard library type
        std_types = {
            "String", "Vec", "HashMap", "Result", "Option", "Box", "Rc", "Arc",
            "str", "u8", "u16", "u32", "u64", "u128", "usize", "i8", "i16", 
            "i32", "i64", "i128", "isize", "f32", "f64", "bool", "char"
        }
        
        if ref_name in std_types:
            return f"std::{ref_name}"
        
        # For other unqualified references, we might need more context
        # For now, return as-is but this could be improved with use declaration tracking
        return ref_name

    def process_component(comp, parent_path=""):
        comp_name = comp.get("name", "")
        comp_type = comp.get("type", "")
        
        if not comp_name:
            return
        
        # Build the full path for this component
        if parent_path:
            full_name = f"{parent_path}::{comp_name}"
        else:
            full_name = f"{base_module_path}::{comp_name}"
        
        # Handle special cases for top-level items in main.rs or lib.rs
        if base_module_path == crate_name and not parent_path:
            full_name = f"{crate_name}::{comp_name}"
        
        if comp_type == "function_item":
            process_function(comp, full_name)
        elif comp_type == "struct_item":
            process_struct(comp, full_name)
        elif comp_type == "enum_item":
            process_enum(comp, full_name)
        elif comp_type == "impl_item":
            process_impl(comp, full_name, parent_path)
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

        # Process children with the current full_name as parent
        for child in comp.get("children", []):
            process_component(child, full_name)

    def process_function(comp, full_name):
        fn_node = add_node(full_name, "function", {
            "signature": [param.get("name", "") for param in comp.get("parameters", [])],
            "return_type": comp.get("return_type"),
            "visibility": comp.get("visibility", "private"),
            "type_parameters": comp.get("type_parameters"),
            "where_clause": comp.get("where_clause"),
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")  # Store simple name for easier querying
        })

        # Process parameters
        for param in comp.get("parameters", []):
            param_name = param.get("name", "")
            param_type = param.get("type", "")
            if param_name and param_name != "self":
                param_node_name = f"{full_name}::{param_name}"
                add_node(param_node_name, "parameter", {
                    "type": param_type,
                    "location": get_location_info(comp),
                    "simple_name": param_name
                })
                edges.append({
                    "from": full_name,
                    "to": param_node_name,
                    "relation": "defines"
                })

        # Process function calls
        for call in comp.get("function_calls", []):
            call_info = call if isinstance(call, dict) else {"name": call}
            call_name = call_info.get("name", str(call_info))
            normalized_call = normalize_external_reference(call_name, full_name)
            add_node(normalized_call, "function", {"simple_name": call_name})
            edges.append({
                "from": full_name,
                "to": normalized_call,
                "relation": "calls"
            })

        # Process method calls
        for method_call in comp.get("method_calls", []):
            method_name = method_call.get("method", "")
            receiver = method_call.get("receiver", "")
            if method_name:
                # Create a more descriptive method identifier
                if receiver:
                    full_method_name = f"{receiver}::{method_name}"
                else:
                    full_method_name = f"<unknown>::{method_name}"
                
                add_node(full_method_name, "method", {"simple_name": method_name})
                edges.append({
                    "from": full_name,
                    "to": full_method_name,
                    "relation": "calls"
                })

        # Process macro calls
        for macro_call in comp.get("macro_calls", []):
            macro_name = macro_call.get("name", str(macro_call))
            normalized_macro = normalize_external_reference(macro_name, full_name)
            add_node(normalized_macro, "macro", {"simple_name": macro_name})
            edges.append({
                "from": full_name,
                "to": normalized_macro,
                "relation": "invokes"
            })

        # Process variables
        for var in comp.get("variables", []):
            var_name = var.get("name", "")
            var_type = var.get("type", "")
            if var_name:
                var_node_name = f"{full_name}::{var_name}"
                add_node(var_node_name, "variable", {
                    "type": var_type,
                    "value": var.get("value"),
                    "location": get_location_info(comp),
                    "simple_name": var_name
                })
                edges.append({
                    "from": full_name,
                    "to": var_node_name,
                    "relation": "defines"
                })

        # Process types used
        for type_used in comp.get("types_used", []):
            normalized_type = normalize_external_reference(type_used, full_name)
            add_node(normalized_type, "type", {"simple_name": type_used})
            edges.append({
                "from": full_name,
                "to": normalized_type,
                "relation": "uses"
            })

    def process_struct(comp, full_name):
        struct_node = add_node(full_name, "struct", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")
        })

        # Process fields
        for field in comp.get("fields", []):
            field_name = field.get("name", "")
            field_type = field.get("type", "")
            if field_name:
                field_node_name = f"{full_name}::{field_name}"
                add_node(field_node_name, "field", {
                    "type": field_type,
                    "visibility": field.get("visibility", "private"),
                    "location": get_location_info(comp),
                    "simple_name": field_name
                })
                edges.append({
                    "from": full_name,
                    "to": field_node_name,
                    "relation": "has_field"
                })

                if field_type:
                    normalized_type = normalize_external_reference(field_type, full_name)
                    add_node(normalized_type, "type", {"simple_name": field_type})
                    edges.append({
                        "from": full_name,
                        "to": normalized_type,
                        "relation": "depends_on"
                    })

    def process_enum(comp, full_name):
        enum_node = add_node(full_name, "enum", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")
        })

        # Process variants
        for variant in comp.get("variants", []):
            variant_name = variant.get("name", "")
            if variant_name:
                variant_node_name = f"{full_name}::{variant_name}"
                add_node(variant_node_name, "variant", {
                    "location": get_location_info(comp),
                    "simple_name": variant_name
                })
                edges.append({
                    "from": full_name,
                    "to": variant_node_name,
                    "relation": "has_variant"
                })

                # Process variant fields
                for field in variant.get("fields", []):
                    field_name = field.get("name", "")
                    field_type = field.get("type", "")
                    if field_name:
                        field_node_name = f"{variant_node_name}::{field_name}"
                        add_node(field_node_name, "field", {
                            "type": field_type,
                            "location": get_location_info(comp),
                            "simple_name": field_name
                        })
                        edges.append({
                            "from": variant_node_name,
                            "to": field_node_name,
                            "relation": "has_field"
                        })

                        if field_type:
                            normalized_type = normalize_external_reference(field_type, variant_node_name)
                            add_node(normalized_type, "type", {"simple_name": field_type})
                            edges.append({
                                "from": variant_node_name,
                                "to": normalized_type,
                                "relation": "depends_on"
                            })

    def process_impl(comp, full_name, parent_path):
        trait_name = comp.get("trait_name", "")
        type_name = comp.get("type_name", "")
        
        if trait_name and type_name:
            impl_id = f"impl {trait_name} for {type_name}"
            full_impl_path = f"{base_module_path}::{impl_id}"
        elif type_name:
            impl_id = f"impl {type_name}"
            full_impl_path = f"{base_module_path}::{impl_id}"
        else:
            full_impl_path = full_name
        
        impl_node = add_node(full_impl_path, "impl", {
            "type_parameters": comp.get("type_parameters"),
            "location": get_location_info(comp),
            "trait_name": trait_name,
            "type_name": type_name
        })

        if trait_name:
            normalized_trait = normalize_external_reference(trait_name, full_impl_path)
            add_node(normalized_trait, "trait", {"simple_name": trait_name})
            edges.append({
                "from": full_impl_path,
                "to": normalized_trait,
                "relation": "implements"
            })
        
        if type_name:
            normalized_type = normalize_external_reference(type_name, full_impl_path)
            add_node(normalized_type, "type", {"simple_name": type_name})
            edges.append({
                "from": full_impl_path,
                "to": normalized_type,
                "relation": "for_type"
            })

    def process_trait(comp, full_name):
        trait_node = add_node(full_name, "trait", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")
        })

        for bound in comp.get("trait_bounds", []):
            normalized_bound = normalize_external_reference(bound, full_name)
            add_node(normalized_bound, "trait", {"simple_name": bound})
            edges.append({
                "from": full_name,
                "to": normalized_bound,
                "relation": "extends"
            })

    def process_module(comp, full_name):
        mod_node = add_node(full_name, "module", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")
        })

    def process_use_declaration(comp, full_name):
        use_id = f"use {comp.get('import_path', full_name)}"
        use_full_path = f"{base_module_path}::{use_id}"
        
        use_node = add_node(use_full_path, "import", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp),
            "import_path": comp.get("import_path", "")
        })

        for import_path in comp.get("imports", []):
            add_node(import_path, "module", {"simple_name": import_path.split("::")[-1]})
            edges.append({
                "from": use_full_path,
                "to": import_path,
                "relation": "imports"
            })

    def process_const(comp, full_name):
        const_node = add_node(full_name, "const", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")
        })

        for type_used in comp.get("types_used", []):
            normalized_type = normalize_external_reference(type_used, full_name)
            add_node(normalized_type, "type", {"simple_name": type_used})
            edges.append({
                "from": full_name,
                "to": normalized_type,
                "relation": "uses"
            })

    def process_static(comp, full_name):
        static_node = add_node(full_name, "static", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")
        })

        for type_used in comp.get("types_used", []):
            normalized_type = normalize_external_reference(type_used, full_name)
            add_node(normalized_type, "type", {"simple_name": type_used})
            edges.append({
                "from": full_name,
                "to": normalized_type,
                "relation": "uses"
            })

    def process_type_alias(comp, full_name):
        alias_node = add_node(full_name, "type_alias", {
            "visibility": comp.get("visibility", "private"),
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")
        })

        for type_used in comp.get("types_used", []):
            normalized_type = normalize_external_reference(type_used, full_name)
            add_node(normalized_type, "type", {"simple_name": type_used})
            edges.append({
                "from": full_name,
                "to": normalized_type,
                "relation": "aliases"
            })

    def process_associated_type(comp, full_name, parent_path):
        assoc_type_node = add_node(full_name, "associated_type", {
            "location": get_location_info(comp),
            "simple_name": comp.get("name", "")
        })

        if parent_path:
            edges.append({
                "from": parent_path,
                "to": full_name,
                "relation": "defines"
            })

        for type_used in comp.get("types_used", []):
            normalized_type = normalize_external_reference(type_used, full_name)
            add_node(normalized_type, "type", {"simple_name": type_used})
            edges.append({
                "from": full_name,
                "to": normalized_type,
                "relation": "uses"
            })

    for comp in raw_components:
        process_component(comp)

    for comp in raw_components:
        comp_name = comp.get("name", "")
        if comp_name:
            full_comp_name = f"{base_module_path}::{comp_name}"
            if full_comp_name in seen_nodes:
                for lifetime in comp.get("lifetimes", []):
                    lifetime_id = f"'{lifetime}"
                    add_node(lifetime_id, "lifetime", {"simple_name": lifetime})
                    edges.append({
                        "from": full_comp_name,
                        "to": lifetime_id,
                        "relation": "uses"
                    })
    print(f"Processed {len(nodes)} nodes and {len(edges)} edges for Rust components.")
    return {"nodes": nodes, "edges": edges}