import re
from collections import defaultdict
from tqdm import tqdm

def extract_rust_id(comp):
    """
    Builds a stable ID in the format: "full_module_path::component_name".
    This function extracts the module path from resolved imports or builds it from the component context.
    """
    name_part = comp.get("name") or "<unnamed>"
    
    # Try to get the full module path from various sources
    # Priority: resolved module_name > constructed path from current context
    module_part = None
    
    # For function calls and method calls, we already have resolved module_name
    if comp.get("module_name"):
        module_part = comp.get("module_name")
    else:
        # For component definitions, we need to construct the module path
        # This should be enhanced based on your extractor's module tracking
        module_part = comp.get("module_path") or "<anonymous_module>"
    last_module_segment = module_part.split('::')[-1]
    return f"{last_module_segment}::{name_part}"

def build_module_path_for_component(comp, current_module_stack=[]):
    """
    Build the full module path for a component based on its context.
    This should match the import resolution logic from the extractor.
    """
    # If the component already has a resolved module path, use it
    if comp.get("resolved_module_path"):
        return comp["resolved_module_path"]
    
    # Otherwise, construct from the current module context
    # This is a simplified version - you might need to enhance this based on your needs
    name = comp.get("name", "")
    if current_module_stack:
        return "::".join(current_module_stack + [name])
    else:
        return name

def adapt_rust_components(raw_components: list) -> dict:
    """
    Adapts raw Rust components into a unified schema using full module paths.
    
    This adapter creates nodes with IDs in the format: full_module_path::component_name
    where full_module_path is the resolved import path (e.g., api::x::y::g::f::q).
    """
    nodes = {}
    edges = []
    
    # --- Pass 1: Flatten hierarchy and build module context ---
    all_components = []
    component_queue = list(raw_components)
    module_stack = []  # Track current module nesting
    
    def process_component_tree(comps, current_module_path=[]):
        for comp in comps:
            # Update module path context
            comp_module_path = current_module_path.copy()
            if comp.get('type') == 'mod_item':
                comp_module_path.append(comp.get('name', ''))
            
            comp['current_module_path'] = comp_module_path
            
            # Process children with updated context
            children = comp.pop('children', [])
            if children:
                process_component_tree(children, comp_module_path)
            
            all_components.append(comp)
    
    process_component_tree(raw_components)

    # Pre-calculate mapping from simple names to fully-qualified IDs
    name_to_fq_ids = defaultdict(list)
    
    for comp in all_components:
        comp_type = comp.get('type')
        name = comp.get('name')
        
        if comp_type in {'function_item', 'struct_item', 'enum_item', 'trait_item', 'impl_item', 'mod_item'}:
            # Build the full module path for this component
            if comp.get('current_module_path'):
                # Use the tracked module path
                module_path = "::".join(comp['current_module_path'])
                if module_path:
                    fq_id = f"{module_path}::{name}"
                else:
                    fq_id = name
            else:
                fq_id = name
            
            comp['fq_id'] = fq_id
            if name:
                name_to_fq_ids[name].append(fq_id)

    # --- Pass 2: Create nodes and edges ---
    for comp in tqdm(all_components, desc="Adapting Rust components"):
        comp_type = comp.get('type')
        
        # Create nodes for primary component types
        if comp_type in {'function_item', 'struct_item', 'enum_item', 'trait_item', 'impl_item', 'mod_item'}:
            fq_id = comp.get('fq_id')
            if fq_id:
                nodes[fq_id] = {
                    "id": fq_id,
                    "category": comp_type,
                    "name": comp.get('name'),
                    "file_path": comp.get('file_path'),
                    "start": comp.get('span', {}).get('start_line', 0),
                    "end": comp.get('span', {}).get('end_line', 0)
                }

        # Create 'calls' edges using resolved module names
        source_id = comp.get('fq_id') or comp.get('name', 'unknown')
        
        # Process function calls with resolved module paths
        for call in comp.get('function_calls', []):
            call_name = call.get('name')
            resolved_module = call.get('module_name')  # This comes from our enhanced extractor
            
            if resolved_module and resolved_module != call_name:
                # Use the fully resolved module path
                target_id = resolved_module
            else:
                # Fall back to simple name matching
                target_id = call_name
            
            if target_id:
                edges.append({
                    "from": source_id,
                    "to": target_id,
                    "relation": "calls"
                })

        # Process method calls with resolved module paths
        for call in comp.get('method_calls', []):
            method_name = call.get('method')
            resolved_module = call.get('module_name')  # Full path like api::x::y::g::f::q::method
            
            if resolved_module:
                target_id = resolved_module
            else:
                # Fall back to receiver::method format
                receiver = call.get('receiver', '')
                target_id = f"{receiver}::{method_name}" if receiver else method_name
            
            if target_id:
                edges.append({
                    "from": source_id,
                    "to": target_id,
                    "relation": "calls"
                })

        # Process macro calls with resolved module paths
        for call in comp.get('macro_calls', []):
            macro_name = call.get('name')
            resolved_module = call.get('module_name')
            
            target_id = resolved_module if resolved_module else macro_name
            if target_id:
                edges.append({
                    "from": source_id,
                    "to": target_id,
                    "relation": "calls"
                })

        # Create 'imports' edges from use declarations
        if comp_type == 'use_declaration':
            for import_path in comp.get('imports', []):
                edges.append({
                    "from": source_id,
                    "to": import_path,
                    "relation": "imports"
                })

        # Create 'uses_type' edges for type dependencies
        for type_info in comp.get('types_used', []):
            if isinstance(type_info, dict):
                type_name = type_info.get('name')
                resolved_type = type_info.get('module_name')
                target_id = resolved_type if resolved_type else type_name
            else:
                # Handle legacy format where types_used might be strings
                target_id = str(type_info)
            
            if target_id:
                edges.append({
                    "from": source_id,
                    "to": target_id,
                    "relation": "uses_type"
                })

    # --- Pass 3: Create stub nodes for external references ---
    final_nodes = list(nodes.values())
    seen_ids = set(nodes.keys())

    for edge in edges:
        for endpoint_key in ("from", "to"):
            endpoint_id = edge[endpoint_key]
            if endpoint_id not in seen_ids:
                # Determine category for external references
                category = "external_reference"
                if "::" in endpoint_id:
                    if edge["relation"] == "calls":
                        category = "external_function"
                    elif edge["relation"] == "uses_type":
                        category = "external_type"
                    elif edge["relation"] == "imports":
                        category = "external_module"
                
                # Extract the simple name (last part after ::)
                simple_name = endpoint_id.split("::")[-1]
                
                final_nodes.append({
                    "id": endpoint_id,
                    "category": category,
                    "name": simple_name
                })
                seen_ids.add(endpoint_id)

    print(f"Created {len(final_nodes)} nodes and {len(edges)} edges.")
    
    # Show some examples for debugging
    print("\nSample nodes:")
    for i, node in enumerate(final_nodes[:5]):
        print(f"  {node}")
    
    print(f"\nSample edges:")
    for i, edge in enumerate(edges[:5]):
        print(f"  {edge}")
    
    return {"nodes": final_nodes, "edges": edges}