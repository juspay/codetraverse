import re
from collections import defaultdict
from tqdm import tqdm

def extract_rust_id(comp):
    """
    Builds a stable ID in the format: "module_path::component_name".
    Uses the module_path field provided by the enhanced extractor.
    """
    module_path = comp.get("module_path", "unknown_module")
    name = comp.get("name", "unnamed")
    
    # The line number is kept to prevent collisions with identically named items
    # (e.g., multiple functions in an `impl` block)
    line_num = comp.get('span', {}).get('start_line', 0)

    return f"{module_path}::{name}@{line_num}"


def adapt_rust_components(raw_components: list) -> dict:
    """
    Adapts raw Rust components into a simple, unified schema using module paths.

    This adapter uses a simple, two-pass approach:
    1. It iterates through all components to create primary nodes using a
       module_path::component_name ID format and gathers all potential edges.
    2. It creates "stub" nodes for any dependency that was not defined in the project.
    
    The component extractor now provides full module paths for proper resolution.
    """
    nodes = {}
    edges = []
    
    # --- Pass 1: Create primary nodes and gather all potential edges ---

    # Flatten the component hierarchy first to process all items
    all_components = []
    component_queue = list(raw_components)
    while component_queue:
        comp = component_queue.pop(0)
        children = comp.pop('children', [])
        if children:
            component_queue.extend(children)
        all_components.append(comp)

    # Pre-calculate maps for name resolution
    name_to_ids = defaultdict(list)  # Simple name -> list of full IDs
    resolved_name_to_ids = defaultdict(list)  # Resolved name -> list of full IDs
    
    for comp in all_components:
        comp['id'] = extract_rust_id(comp)
        name = comp.get('name')
        if name:
            name_to_ids[name].append(comp['id'])

    for comp in tqdm(all_components, desc="Adapting Rust components"):
        source_id = comp['id']
        comp_type = comp.get('type')
        
        # 1a) Create a primary node for key component types
        if comp_type in {'function_item', 'struct_item', 'enum_item', 'trait_item', 'impl_item', 'mod_item'}:
            nodes[source_id] = {
                "id":        source_id,
                "category":  comp_type,
                "name":      comp.get('name'),
                "module_path": comp.get('module_path'),
                "file_path": comp.get('file_path'),
                "start":     comp.get('span', {}).get('start_line', 0),
                "end":       comp.get('span', {}).get('end_line', 0)
            }

        # 1b) Create 'calls' edges using resolved names when available
        function_calls = comp.get('function_calls', [])
        method_calls = comp.get('method_calls', [])
        
        for call in function_calls:
            original_name = call.get('name')
            resolved_name = call.get('resolved_name')
            
            if not original_name:
                continue
                
            # Use resolved name if available, otherwise use original
            target_name = resolved_name if resolved_name and resolved_name != original_name else original_name
            
            # Try to find exact matches first
            potential_targets = []
            
            # Look for exact matches in our component list
            for candidate_comp in all_components:
                candidate_module = candidate_comp.get('module_path', '')
                candidate_name = candidate_comp.get('name', '')
                candidate_full_name = f"{candidate_module}::{candidate_name}"
                
                if (candidate_full_name == target_name or 
                    candidate_name == target_name or
                    candidate_name == original_name):
                    potential_targets.append(candidate_comp['id'])
            
            if potential_targets:
                for target_id in potential_targets:
                    edges.append({"from": source_id, "to": target_id, "relation": "calls"})
            else:
                # Create stub edge with the most specific name we have
                edges.append({"from": source_id, "to": target_name, "relation": "calls"})
        
        for call in method_calls:
            method_name = call.get('method')
            full_path = call.get('full_path')
            resolved_receiver = call.get('resolved_receiver')
            
            if not method_name:
                continue
                
            # Use the full path if available
            target_name = full_path if full_path else f"{resolved_receiver}::{method_name}" if resolved_receiver else method_name
            
            # Look for matches
            potential_targets = []
            for candidate_comp in all_components:
                candidate_module = candidate_comp.get('module_path', '')
                candidate_name = candidate_comp.get('name', '')
                candidate_full_name = f"{candidate_module}::{candidate_name}"
                
                if (candidate_full_name == target_name or 
                    candidate_name == method_name):
                    potential_targets.append(candidate_comp['id'])
            
            if potential_targets:
                for target_id in potential_targets:
                    edges.append({"from": source_id, "to": target_id, "relation": "calls"})
            else:
                edges.append({"from": source_id, "to": target_name, "relation": "calls"})

        # 1c) Create 'imports' edges from 'use' declarations
        if comp_type == 'use_declaration':
            for import_path in comp.get('imports', []):
                # Try to find the imported item in our components
                potential_targets = []
                import_parts = import_path.split('::')
                if import_parts:
                    imported_name = import_parts[-1]
                    
                    for candidate_comp in all_components:
                        candidate_module = candidate_comp.get('module_path', '')
                        candidate_name = candidate_comp.get('name', '')
                        candidate_full_name = f"{candidate_module}::{candidate_name}"
                        
                        if (candidate_full_name == import_path or 
                            candidate_name == imported_name):
                            potential_targets.append(candidate_comp['id'])
                
                if potential_targets:
                    for target_id in potential_targets:
                        edges.append({"from": source_id, "to": target_id, "relation": "imports"})
                else:
                    edges.append({"from": source_id, "to": import_path, "relation": "imports"})

        # 1d) Create 'uses_type' edges for type usage
        types_used = comp.get('types_used', [])
        for type_info in types_used:
            if isinstance(type_info, dict):
                original_type = type_info.get('type')
                resolved_type = type_info.get('resolved_type')
                target_type = resolved_type if resolved_type and resolved_type != original_type else original_type
            else:
                # Handle old format where types_used was just a list of strings
                target_type = type_info
            
            if target_type:
                # Look for type definitions
                potential_targets = []
                for candidate_comp in all_components:
                    if candidate_comp.get('type') in {'struct_item', 'enum_item', 'trait_item', 'type_alias_item'}:
                        candidate_module = candidate_comp.get('module_path', '')
                        candidate_name = candidate_comp.get('name', '')
                        candidate_full_name = f"{candidate_module}::{candidate_name}"
                        
                        if (candidate_full_name == target_type or
                            candidate_name == target_type):
                            potential_targets.append(candidate_comp['id'])
                
                if potential_targets:
                    for target_id in potential_targets:
                        edges.append({"from": source_id, "to": target_id, "relation": "uses_type"})
                else:
                    edges.append({"from": source_id, "to": target_type, "relation": "uses_type"})

    # --- Pass 2: Create stub nodes for any edge endpoint that doesn't exist ---
    final_nodes = list(nodes.values())
    seen_ids = set(nodes.keys())

    for edge in edges:
        for endpoint_key in ("from", "to"):
            endpoint_id = edge[endpoint_key]
            if endpoint_id not in seen_ids:
                # Extract a reasonable name from the ID
                name_part = endpoint_id.split('::')[-1].split('@')[0]
                final_nodes.append({
                    "id": endpoint_id, 
                    "category": "external_reference",
                    "name": name_part,
                    "module_path": "::".join(endpoint_id.split('::')[:-1]) if '::' in endpoint_id else endpoint_id
                })
                seen_ids.add(endpoint_id)

    print(f"Created {len(final_nodes)} nodes and {len(edges)} edges.")
    
    # Print sample nodes for debugging
    print("\nSample nodes:")
    for i, node in enumerate(final_nodes[:10]):
        print(f"{i+1}. {node}")
    
    print(f"\nSample edges:")
    for i, edge in enumerate(edges[:10]):
        print(f"{i+1}. {edge}")
    
    return {"nodes": final_nodes, "edges": edges}