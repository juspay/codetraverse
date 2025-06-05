import os
import json
import networkx as nx
from tqdm import tqdm

def load_components(fdep_dir):
    components = {}
    for dirpath, _, files in os.walk(fdep_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            full = os.path.join(dirpath, fn)
            with open(full, "r", encoding="utf-8") as f:
                data = json.load(f)
            for comp in data:
                # Use a unique identifier for each component
                comp_id = _get_component_id(comp)
                components[comp_id] = comp
    return components

def _get_component_id(comp):
    """Generate a unique identifier for a component"""
    kind = comp.get("kind", "unknown")
    name = comp.get("name", "")
    tag_name = comp.get("tag_name", "")
    file_name = comp.get("file_name", "")
    start_line = comp.get("start_line", 0)
    
    if kind == "jsx":
        # For JSX components, use tag_name as primary identifier
        return f"{tag_name}_{file_name}_{start_line}" if tag_name else f"jsx_{file_name}_{start_line}"
    else:
        # For other components (functions, modules, types), use name
        return f"{name}_{file_name}_{start_line}" if name else f"{kind}_{file_name}_{start_line}"

def build_graph(components):
    G = nx.DiGraph()
    
    # Add nodes for all components
    for comp_id, comp in tqdm(components.items(), desc="Adding nodes"):
        kind = comp.get("kind", "unknown")
        
        # Base attributes for all component types
        node_attrs = {
            "kind": kind,
            "file_name": comp.get("file_name", ""),
            "start_line": comp.get("start_line", 0),
            "end_line": comp.get("end_line", 0),
            "function_calls": json.dumps([
                c["name"] if isinstance(c, dict) else c
                for c in comp.get("function_calls", [])
            ]),
            "literals": json.dumps(comp.get("literals", []))
        }
        
        # Add kind-specific attributes
        if kind == "jsx":
            node_attrs.update({
                "tag_name": comp.get("tag_name", ""),
                "attributes": json.dumps(comp.get("attributes", [])),
                "jsx_elements": json.dumps(comp.get("jsx_elements", []))
            })
        elif kind in ["function", "variable"]:
            node_attrs.update({
                "name": comp.get("name", ""),
                "type_signature": comp.get("type_signature", ""),
                "type_dependencies": json.dumps(comp.get("type_dependencies", [])),
                "parameters": json.dumps(comp.get("parameters", [])),
                "parameter_type_annotations": json.dumps(comp.get("parameter_type_annotations", {})),
                "return_type_annotation": comp.get("return_type_annotation", ""),
                "local_variables": json.dumps([
                    lv.get("name", "") for lv in comp.get("local_variables", [])
                ]),
                "jsx_elements": json.dumps([
                    jsx.get("tag_name", "") for jsx in comp.get("jsx_elements", [])
                ])
            })
        elif kind == "module":
            node_attrs.update({
                "name": comp.get("name", ""),
                "elements": json.dumps([
                    elem.get("name", elem.get("tag_name", "")) 
                    for elem in comp.get("elements", [])
                ])
            })
        elif kind == "type":
            node_attrs.update({
                "name": comp.get("name", ""),
                "subkind": comp.get("subkind", ""),
                "fields": json.dumps(comp.get("fields", [])),
                "variants": json.dumps(comp.get("variants", []))
            })
        elif kind == "external":
            node_attrs.update({
                "name": comp.get("name", ""),
                "type": comp.get("type", "")
            })
        else:
            # Fallback for other kinds
            node_attrs["name"] = comp.get("name", "")
        
        G.add_node(comp_id, **node_attrs)
    
    # Add edges based on relationships
    for comp_id, comp in tqdm(components.items(), desc="Adding edges"):
        _add_component_edges(G, comp_id, comp, components)
    
    return G

def _add_component_edges(G, comp_id, comp, all_components):
    """Add edges for a component based on its relationships"""
    
    # Add edges for function calls
    for call in comp.get("function_calls", []):
        callee_name = call["name"] if isinstance(call, dict) else call
        # Try to find the target component
        target_id = _find_component_by_name(callee_name, all_components)
        if target_id:
            G.add_edge(comp_id, target_id, relation="calls")
        else:
            # Add external node if not found
            if not G.has_node(callee_name):
                G.add_node(callee_name, kind="external_reference", name=callee_name)
            G.add_edge(comp_id, callee_name, relation="calls")
    
    # Add edges for JSX element usage
    if comp.get("kind") in ["function", "variable"]:
        for jsx_elem in comp.get("jsx_elements", []):
            jsx_tag = jsx_elem.get("tag_name", "") if isinstance(jsx_elem, dict) else jsx_elem
            if jsx_tag:
                # Try to find the JSX component
                target_id = _find_jsx_component_by_tag(jsx_tag, all_components)
                if target_id:
                    G.add_edge(comp_id, target_id, relation="uses_jsx")
                else:
                    # Add external JSX node if not found
                    jsx_node_id = f"jsx_external_{jsx_tag}"
                    if not G.has_node(jsx_node_id):
                        G.add_node(jsx_node_id, kind="external_jsx", tag_name=jsx_tag)
                    G.add_edge(comp_id, jsx_node_id, relation="uses_jsx")
    
    # Add edges for local variables (nested relationships)
    for local_var in comp.get("local_variables", []):
        if isinstance(local_var, dict):
            local_var_name = local_var.get("name", "")
            if local_var_name:
                local_id = f"{local_var_name}_{comp.get('file_name', '')}_{local_var.get('start_line', 0)}"
                if not G.has_node(local_id):
                    G.add_node(local_id, 
                              kind=local_var.get("kind", "local_variable"),
                              name=local_var_name,
                              parent_component=comp_id)
                G.add_edge(comp_id, local_id, relation="contains")

def _find_component_by_name(name, all_components):
    """Find a component by its name"""
    for comp_id, comp in all_components.items():
        if comp.get("name") == name:
            return comp_id
    return None

def _find_jsx_component_by_tag(tag_name, all_components):
    """Find a JSX component by its tag name"""
    for comp_id, comp in all_components.items():
        if comp.get("kind") == "jsx" and comp.get("tag_name") == tag_name:
            return comp_id
    return None

def build_graph_from_schema(schema):
    G = nx.DiGraph()

    for node in schema["nodes"]:
        nid = node["id"]
        attrs = {}
        for k, v in node.items():
            if k == "id":
                continue
            if isinstance(v, (str, int, float, bool)):
                attrs[k] = v
            else:
                attrs[k] = json.dumps(v)
        G.add_node(nid, **attrs)

    for edge in schema["edges"]:
        src = edge["from"]
        dst = edge["to"]
        rel = edge.get("relation")
        G.add_edge(src, dst, relation=rel)
    return G

def export_graph_to_schema(G):
    """Export NetworkX graph to schema format"""
    nodes = []
    edges = []
    
    for node_id, attrs in G.nodes(data=True):
        node_data = {"id": node_id}
        for k, v in attrs.items():
            # Try to parse JSON strings back to objects
            if isinstance(v, str) and v.startswith(('[', '{')):
                try:
                    node_data[k] = json.loads(v)
                except json.JSONDecodeError:
                    node_data[k] = v
            else:
                node_data[k] = v
        nodes.append(node_data)
    
    for src, dst, attrs in G.edges(data=True):
        edge_data = {
            "from": src,
            "to": dst,
            "relation": attrs.get("relation", "unknown")
        }
        edges.append(edge_data)
    
    return {"nodes": nodes, "edges": edges}

def analyze_jsx_usage(G):
    """Analyze JSX component usage patterns"""
    jsx_nodes = [n for n, attrs in G.nodes(data=True) if attrs.get("kind") == "jsx"]
    jsx_usage = {}
    
    for jsx_node in jsx_nodes:
        tag_name = G.nodes[jsx_node].get("tag_name", "")
        # Find all components that use this JSX element
        users = [n for n in G.predecessors(jsx_node)]
        jsx_usage[tag_name] = {
            "node_id": jsx_node,
            "used_by": users,
            "usage_count": len(users)
        }
    
    return jsx_usage