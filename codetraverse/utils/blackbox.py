import os
import json
from typing import List, Dict, Any
import networkx as nx
from codetraverse.path import load_graph
from collections import deque

def getModuleInfo(fdep_folder: str, module_name: str) -> List[Dict[str, Any]]:
    
    def normalize_path(path: str) -> str:
        if not path:
            return ""
        path = os.path.splitext(path)[0]
        return path.replace('\\', '/').strip('/')
    
    def generate_patterns(module_name: str) -> List[str]:
        """Generate patterns for the exact module path."""
        norm = normalize_path(module_name)
        return [norm]  # Return only the normalized absolute path

    def matches_pattern(module_path: str, patterns: List[str]) -> bool:
        """Check if module_path matches any pattern."""
        norm_path = normalize_path(module_path)
        
        for pattern in patterns:
            norm_pattern = normalize_path(pattern)
            # Strict match: Only return True if the paths are exactly the same
            if norm_path == norm_pattern:
                return True
        return False
    
    def extract_components(data, patterns: List[str]) -> List[Dict[str, Any]]:
        """Recursively extract matching components from data."""
        components = []
        
        def traverse(obj):
            if isinstance(obj, dict):
                if 'module' in obj and matches_pattern(obj['module'], patterns):
                    components.append(obj)
                for value in obj.values():
                    traverse(value)
            elif isinstance(obj, list):
                for item in obj:
                    traverse(item)
        
        traverse(data)
        return components
    
    if not os.path.exists(fdep_folder):
        return []
    
    patterns = generate_patterns(module_name)
    all_components = []
    
    # Walk through all JSON files
    for root, _, files in os.walk(fdep_folder):
        for file in files:
            if file.endswith('.json'):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    all_components.extend(extract_components(data, patterns))
                except (json.JSONDecodeError, FileNotFoundError, IOError):
                    continue
    
    seen = set()
    unique_components = []
    for comp in all_components:
        key = (comp.get('kind'), comp.get('name'), comp.get('full_component_path'), 
               comp.get('start_line'), comp.get('end_line'), comp.get('file_path'))
        if key not in seen:
            seen.add(key)
            unique_components.append(comp)
    
    return unique_components

def debug_getModuleInfo(fdep_folder: str, module_name: str) -> List[Dict[str, Any]]:
    print(f"🔍 Searching for: '{module_name}' in {fdep_folder}")
    if not os.path.exists(fdep_folder):
        print(f"Folder doesn't exist: {fdep_folder}")
        return []
    components = getModuleInfo(fdep_folder, module_name)
    if components:
        for comp in components:
            print(f"  - {comp.get('kind', '?')}: {comp.get('name', '?')} "
                  f"(module: {comp.get('module', '?')})")
    else:
        print("❌ No components found")
    return components

def getFunctionInfo(fdep_folder: str, module_name:str, component_name: str, component_type='function') -> List[Dict[str, Any]]:
    if not os.path.exists(fdep_folder):
        print(f"Folder doesn't exist: {fdep_folder}")
        return []
    components = getModuleInfo(fdep_folder, module_name)
    for comp in components:
        if comp.get('kind') == component_type and comp.get('name') == component_name:
            print(json.dumps(comp, indent=2))
            return [comp]
    print(f"❌ Function '{component_name}' not found in module '{module_name}''")
    return []

def getFunctionChildren(graph_path: str, module_name: str, component_name: str, depth: int = 1) -> List[List[Any]]:
    G = load_graph(graph_path)
    if not G:
        print(f"❌ Graph not found at {graph_path}")
        return []
    target = f"{module_name}::{component_name}"
    if target not in G:
        print(f"Error: target '{target}' not in graph.")
        return []
    
    result = []
    visited = set()
    queue = deque([(target, 0)])
    visited.add(target)
    while queue:
        current_node, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
            
        for child in G.successors(current_node):
            if child not in visited:
                visited.add(child)
                child_depth = current_depth + 1
                if "::" in child:
                    child_module, child_component = child.split("::", 1)
                else:
                    child_module, child_component = "", child
                result.append([child, child_module, child_component, child_depth])
                if child_depth < depth:
                    queue.append((child, child_depth))
    return result

def getFunctionParent(graph_path: str, module_name: str, component_name: str, depth: int = 1) -> List[List[Any]]:
    G = load_graph(graph_path)
    if not G:
        print(f"❌ Graph not found at {graph_path}")
        return []
    
    target = f"{module_name}::{component_name}"
    if target not in G:
        print(f"Error: target '{target}' not in graph.")
        return []
    
    result = []
    visited = set()
    queue = deque([(target, 0)]) 
    visited.add(target)
    
    while queue:
        current_node, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for parent in G.predecessors(current_node):
            if parent not in visited:
                visited.add(parent)
                parent_depth = current_depth + 1
                if "::" in parent:
                    parent_module, parent_component = parent.split("::", 1)
                else:
                    parent_module, parent_component = "", parent
                result.append([parent, parent_module, parent_component, parent_depth])
                if parent_depth < depth:
                    queue.append((parent, parent_depth))
    return result

def getFunctionSubgraph(graph_path: str, module_name: str, component_name: str, parent_depth: int = 1, child_depth: int = 1):
    G = load_graph(graph_path)
    if not G:
        return None
    target = f"{module_name}::{component_name}"
    if target not in G:
        return None
    nodes_to_include = {target}
    parents = getFunctionParent(graph_path, module_name, component_name, parent_depth)
    for parent in parents:
        nodes_to_include.add(parent[0])
    children = getFunctionChildren(graph_path, module_name, component_name, child_depth)
    for child in children:
        nodes_to_include.add(child[0])
    subgraph = G.subgraph(nodes_to_include).copy()
    return subgraph


#### use cases

# if __name__ == "__main__":
#     fdep_folder = "/Users/suryansh.s/codetraverse/fdep_xyne"
#     graph_path = "/Users/suryansh.s/codetraverse/graph_xyne/repo_function_calls.graphml"
#     module_name = "node_modules/typescript/lib/lib.es5.d"
#     component_name = "NumberFormatOptionsUseGroupingRegistry"
    # component_type = "interface"

    # components = debug_getModuleInfo(fdep_folder, module_name)
    # getFunctionInfo(fdep_folder, module_name, component_name, component_type)

    # children = getFunctionParentWithDepth(graph_path, module_name, component_name, depth=100)
    # for child in children:
    #     print(f"Child: {child[0]}, Module: {child[1]}, Component: {child[2]}, Depth: {child[3]}")

    # parents_depth = getFunctionParentWithDepth(graph_path, module_name, component_name, depth=2)
    # for parent in parents_depth:
    #     print(f"Parent: {parent[0]}, Module: {parent[1]}, Component: {parent[2]}, Depth: {parent[3]}")

    # sub_graph = getFunctionSubgraph(graph_path, module_name, component_name, parent_depth=2, child_depth=2)
    # nx.write_graphml(sub_graph, "subgraph.graphml")

