import re
import os

def adapt_typescript_components(raw_components):
    nodes = []
    edges = []

    def make_node_id(comp):
        if comp.get("kind") in ("method", "field"):
            if "module" in comp and "class" in comp and "name" in comp:
                return f'{comp["module"]}::{comp["class"]}::{comp["name"]}'
            else:
                return None
        # Handle namespace kind here for node ID generation
        if comp.get("kind") == "namespace":
            if "module" in comp and "name" in comp:
                return f'{comp["module"]}::{comp["name"]}'
            return None
        if "module" in comp and "name" in comp:
            return f'{comp["module"]}::{comp["name"]}'
        return None


    # 1. Build import map for import resolution
    import_map = {}
    for comp in raw_components:
        if comp.get("kind") == "import":
            module = comp["module"]
            statement = comp["statement"]
            if module not in import_map:
                import_map[module] = {}
            # Named imports
            m = re.match(r"import\s+{([^}]+)}\s+from\s+['\"](.+)['\"]", statement)
            if m:
                names_part, source_part = m.groups()
                source_module = source_part
                if source_module.startswith('.'):
                    abs_importer = os.path.abspath(module)
                    abs_importer_dir = os.path.dirname(abs_importer)
                    # Note: You might need to define `repo_root` if it's used elsewhere
                    # For a general solution, we might just keep relative paths or infer based on common structure
                    repo_root = "" # Placeholder, if not explicitly defined
                    abs_target = os.path.normpath(os.path.join(abs_importer_dir, source_module + '.ts'))
                    rel_target = os.path.relpath(abs_target, repo_root).replace("\\", "/")
                    source_module = rel_target
                else:
                    source_module = source_module + '.ts' # Assume .ts for external modules if no extension
                for name in names_part.split(','):
                    name = name.strip()
                    if ' as ' in name:
                        orig, alias = [n.strip() for n in name.split(' as ')]
                        import_map[module][alias] = (source_module, orig)
                    else:
                        import_map[module][name] = (source_module, name)
                continue
            # Default import
            m = re.match(r"import\s+([a-zA-Z0-9_$]+)\s+from\s+['\"](.+)['\"]", statement)
            if m:
                default_name, source_part = m.groups()
                source_module = source_part
                if source_module.startswith('./'):
                    source_module = os.path.normpath(os.path.join(os.path.dirname(module), source_module[2:] + '.ts')).replace("\\", "/")
                elif source_module.startswith('../'):
                    source_module = os.path.normpath(os.path.join(os.path.dirname(module), source_module + '.ts')).replace("\\", "/")
                else:
                    source_module = source_module + '.ts'
                import_map[module][default_name] = (source_module, 'default')
                continue
            # Namespace import
            m = re.match(r"import\s+\*\s+as\s+([a-zA-Z0-9_$]+)\s+from\s+['\"](.+)['\"]", statement)
            if m:
                namespace, source_part = m.groups()
                source_module = source_part
                if source_module.startswith('./'):
                    source_module = os.path.normpath(os.path.join(os.path.dirname(module), source_module[2:] + '.ts')).replace("\\", "/")
                elif source_module.startswith('../'):
                    source_module = os.path.normpath(os.path.join(os.path.dirname(module), source_module + '.ts')).replace("\\", "/")
                else:
                    source_module = source_module + '.ts'
                import_map[module][namespace] = (source_module, '*')
                continue

    # 2. Build nodes for all main entities
    existing_nodes = set()
    for comp in raw_components:
        kind = comp.get("kind")
        node_id = None
        # For method/field, require "class" and "name"
        if kind in {"method", "field"} and comp.get("class") and comp.get("name"):
            node_id = f'{comp["module"]}::{comp["class"]}::{comp["name"]}'
        # For other entities, require "module" and "name"
        elif kind in {"function", "class", "interface", "type_alias", "enum", "variable", "namespace"} and comp.get("module") and comp.get("name"):
            node_id = f'{comp["module"]}::{comp["name"]}'
        # For function_call nodes with full_component_path
        elif kind == "function_call" and comp.get("full_component_path"):
            node_id = comp["full_component_path"]
        else:
            continue  # skip things without node id

        # Avoid duplicate nodes
        if node_id in existing_nodes:
            continue

        # Determine category based on kind, with specific handling for 'namespace'
        category = kind if kind != "namespace" else "namespace"

        node = {
            "id": node_id,
            "category": category, # Use the determined category
            "signature": comp.get("type_signature"),
            "type_parameters": comp.get("type_parameters"),
            "parameters": comp.get("parameters"),
            "decorators": comp.get("decorators"),
            "location": {
                "start": comp.get("start_line"),
                "end": comp.get("end_line"),
                "module": comp.get("module"),
            },
            "value": comp.get("value") if kind == "variable" else None,
            "bases": comp.get("bases") if kind == "class" else None,
            "implements": comp.get("implements") if kind == "class" else None,
            "extends": comp.get("extends") if kind == "interface" else None,
            
            # New fields from the request
            "members": comp.get("members"), # For enums
            "static": comp.get("static"), # For methods/fields
            "abstract": comp.get("abstract"), # For methods/fields
            "readonly": comp.get("readonly"), # For methods/fields
            "override": comp.get("override"), # For methods/fields
            "getter": comp.get("getter"), # For methods
            "setter": comp.get("setter"), # For methods
            "type_param_constraints": comp.get("type_param_constraints"), # For classes/interfaces/functions/type_aliases
            "index_signatures": comp.get("index_signatures"), # For classes/interfaces
        }
        # Filter out None values
        node = {k: v for k, v in node.items() if v is not None}
        nodes.append(node)
        existing_nodes.add(node_id)


    # 3. Add inheritance (extends) edges for classes
    for comp in raw_components:
        if comp.get("kind") == "class" and comp.get("bases"):
            from_id = make_node_id(comp)
            for base in comp["bases"]:
                # Ensure base is a string, if it's coming from comp.get("bases")
                # The extractor should ideally return strings, but defensive check
                if isinstance(base, str):
                    to_id = f"{comp['module']}::{base}"
                    edges.append({
                        "from": from_id,
                        "to": to_id,
                        "relation": "extends"
                    })
                # Original logic for dict might be for more complex base representations,
                # but based on the extractor, it's currently simple strings. Keeping it
                # commented out for now.
                # elif isinstance(base, dict):
                #     base_name = base.get("name")
                #     base_module = base.get("module", comp.get("module"))
                #     to_id = f"{base_module}::{base_name}"
                #     edges.append({
                #         "from": from_id,
                #         "to": to_id,
                #         "relation": "extends"
                #     })

    # 4. Add implementation (implements) edges for classes
    for comp in raw_components:
        if comp.get("kind") == "class" and comp.get("implements"):
            from_id = make_node_id(comp)
            for iface in comp["implements"]:
                # Ensure iface is a string
                if isinstance(iface, str):
                    to_id = f"{comp['module']}::{iface}"
                    edges.append({
                        "from": from_id,
                        "to": to_id,
                        "relation": "implements"
                    })
                # Original logic for dict (commented out for same reason as above)
                # elif isinstance(iface, dict):
                #     iface_name = iface.get("name")
                #     iface_module = iface.get("module", comp.get("module"))
                #     to_id = f"{iface_module}::{iface_name}"
                #     edges.append({
                #         "from": from_id,
                #         "to": to_id,
                #         "relation": "implements"
                #     })

    # 5. Add inheritance (extends) edges for interfaces (if any)
    for comp in raw_components:
        if comp.get("kind") == "interface" and comp.get("extends"):
            from_id = make_node_id(comp)
            for base in comp["extends"]:
                # Ensure base is a string
                if isinstance(base, str):
                    to_id = f"{comp['module']}::{base}"
                    edges.append({
                        "from": from_id,
                        "to": to_id,
                        "relation": "extends"
                    })
                # Original logic for dict (commented out for same reason as above)
                # elif isinstance(base, dict):
                #     base_name = base.get("name")
                #     base_module = base.get("module", comp.get("module"))
                #     to_id = f"{base_module}::{base_name}"
                #     edges.append({
                #         "from": from_id,
                #         "to": to_id,
                #         "relation": "extends"
                #     })

    # 6. Add function/method/variable/function_call edges
    for comp in raw_components:
        kind = comp.get("kind")
        node_id = make_node_id(comp) if kind in {"function", "method", "variable", "function_call", "namespace"} else None # Added namespace

        if kind in {"function", "method", "variable", "function_call"} and comp.get("function_calls"):
            current_module = comp.get("module")
            module_imports = import_map.get(current_module, {})
            for call in comp["function_calls"]:
                # --- For constructor calls from variable initializers ---
                if call.get("kind") == "constructor_call":
                    class_name = call.get("class_name")
                    # Try to resolve to imported or local class node
                    target_module = module_imports.get(class_name, (current_module, class_name))[0]
                    target_id = f"{target_module}::{class_name}"
                # --- For method/function calls ---
                elif call.get("kind") in ("method_call", "function_call"):
                    object_name = call.get("object")
                    method_name = call.get("method")
                    # Try to resolve to class::method or variable::method
                    # If you track variable types, resolve further, but at least try this:
                    target_id = f"{current_module}::{object_name}.{method_name}"
                    # You may want to cross-reference to find real class::method
                else:
                    target_id = call.get("resolved_callee")
                    if not target_id:
                        fn_name = call.get("name") or call.get("base_name")
                        if '.' in fn_name:
                            ns, base = fn_name.split('.', 1)
                            if ns in module_imports and module_imports[ns][1] == '*':
                                target_module = module_imports[ns][0]
                                target_id = f"{target_module}::{base}"
                            else:
                                target_id = f"{current_module}::{fn_name}"
                        elif fn_name in module_imports:
                            target_module, orig_name = module_imports[fn_name]
                            target_id = f"{target_module}::{orig_name}"
                        else:
                            target_id = f"{current_module}::{fn_name}"
                if node_id and target_id and node_id != target_id:
                    edges.append({
                        "from": node_id,
                        "to": target_id,
                        "relation": "calls"
                    })


    # 7. Ensure all endpoints in edges exist as nodes
    seen_ids = {n["id"] for n in nodes}
    for e in edges:
        for endpoint in (e["from"], e["to"]):
            if endpoint and endpoint not in seen_ids:
                # Try to parse endpoint and guess better category/name
                # Format examples: file.ts::Class::method OR file.ts::object.method OR file.ts::Identifier
                parts = endpoint.split("::")
                node_info = {
                    "id": endpoint
                }
                if len(parts) == 3:
                    file, cls, member = parts
                    if "." in member:
                        # It's likely a method call like object.method
                        node_info["category"] = "function_call"
                        node_info["name"] = member
                        node_info["class"] = cls
                    else:
                        node_info["category"] = "method"
                        node_info["name"] = member
                        node_info["class"] = cls
                elif len(parts) == 2:
                    file, member = parts
                    if "." in member:
                        node_info["category"] = "function_call"
                        node_info["name"] = member
                    else:
                        # Default to variable if it's not a function_call,
                        # but could also be a top-level function or namespace
                        node_info["category"] = "variable" 
                        node_info["name"] = member
                else:
                    node_info["category"] = "unknown"
                
                # Add location if we can infer it from the ID structure
                if len(parts) >= 1:
                    node_info["location"] = {"module": parts[0]}

                nodes.append(node_info)
                seen_ids.add(endpoint)


    filtered_edges = [e for e in edges if e["from"] is not None and e["to"] is not None]

    return {
        "nodes": nodes,
        "edges": filtered_edges
    }
