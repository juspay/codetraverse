import os
import json
from typing import List, Dict, Any
from codetraverse.path import load_graph
from collections import deque
import sys
import argparse 


def getModuleInfo(fdep_folder: str, module_name: str) -> List[Dict[str, Any]]:
    
    def normalize_path(path: str) -> str:
        if not path:
            return ""
        path = os.path.splitext(path)[0]
        return path.replace('\\', '/').strip('/')
    
    def generate_patterns(module_name: str) -> List[str]:
        """Generate patterns for the exact module path."""
        norm = normalize_path(module_name)
        return [norm]

    def matches_pattern(module_path: str, patterns: List[str]) -> bool:
        norm_path = normalize_path(module_path)
        
        for pattern in patterns:
            norm_pattern = normalize_path(pattern)
            if norm_path == norm_pattern:
                return True
        return False
    
    def extract_components(data, patterns: List[str]) -> List[Dict[str, Any]]:
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

def getSubgraph(graph_path: str, module_name: str, component_name: str, parent_depth: int = 1, child_depth: int = 1):
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

def getCommonParents(graph_path: str, module_name1: str, component_name1: str, module_name2: str, component_name2: str) -> List[List[Any]]:
    parents1 = getFunctionParent(graph_path, module_name1, component_name1, depth=float('inf'))
    parents2 = getFunctionParent(graph_path, module_name2, component_name2, depth=float('inf'))
    parents1_set = {parent[0] for parent in parents1}
    parents2_set = {parent[0] for parent in parents2}
    common_parent_ids = parents1_set.intersection(parents2_set)
    parents1_dict = {parent[0]: parent for parent in parents1}
    parents2_dict = {parent[0]: parent for parent in parents2}
    
    common_parents = []
    for parent_id in common_parent_ids:
        parent1_info = parents1_dict[parent_id]
        parent2_info = parents2_dict[parent_id]
        common_parents.append([
            parent_id,
            parent1_info[1],
            parent1_info[2],
            parent1_info[3],
            parent2_info[3] 
        ])
    common_parents.sort(key=lambda x: x[3] + x[4])
    
    return common_parents

def getCommonChildren(graph_path: str, module_name1: str, component_name1: str, module_name2: str, component_name2: str) -> List[List[Any]]:
    children1 = getFunctionChildren(graph_path, module_name1, component_name1, depth=float('inf'))
    children2 = getFunctionChildren(graph_path, module_name2, component_name2, depth=float('inf'))
    children1_set = {child[0] for child in children1}
    children2_set = {child[0] for child in children2}
    common_child_ids = children1_set.intersection(children2_set)
    children1_dict = {child[0]: child for child in children1}
    children2_dict = {child[0]: child for child in children2}
    
    common_children = []
    for child_id in common_child_ids:
        child1_info = children1_dict[child_id]
        child2_info = children2_dict[child_id]
        common_children.append([
            child_id,
            child1_info[1],
            child1_info[2],
            child1_info[3],
            child2_info[3] 
        ])
    common_children.sort(key=lambda x: x[3] + x[4])
    
    return common_children


def main():
    parser = argparse.ArgumentParser(description='Code Analysis Tool')
    subparsers = parser.add_subparsers(dest='function', help='Available functions')
    
    parser_module = subparsers.add_parser('getModuleInfo', help='Get module information')
    parser_module.add_argument('fdep_folder', help='Path to fdep folder')
    parser_module.add_argument('module_name', help='Module name to search for')
    
    parser_func = subparsers.add_parser('getFunctionInfo', help='Get function information')
    parser_func.add_argument('fdep_folder', help='Path to fdep folder')
    parser_func.add_argument('module_name', help='Module name')
    parser_func.add_argument('component_name', help='Component name')
    parser_func.add_argument('--component_type', default='function', help='Component type (default: function)')
    
    parser_children = subparsers.add_parser('getFunctionChildren', help='Get function children')
    parser_children.add_argument('graph_path', help='Path to graph file')
    parser_children.add_argument('module_name', help='Module name')
    parser_children.add_argument('component_name', help='Component name')
    parser_children.add_argument('--depth', type=int, default=1, help='Search depth (default: 1)')
    
    parser_parent = subparsers.add_parser('getFunctionParent', help='Get function parents')
    parser_parent.add_argument('graph_path', help='Path to graph file')
    parser_parent.add_argument('module_name', help='Module name')
    parser_parent.add_argument('component_name', help='Component name')
    parser_parent.add_argument('--depth', type=int, default=1, help='Search depth (default: 1)')
    
    parser_subgraph = subparsers.add_parser('getSubgraph', help='Get subgraph')
    parser_subgraph.add_argument('graph_path', help='Path to graph file')
    parser_subgraph.add_argument('module_name', help='Module name')
    parser_subgraph.add_argument('component_name', help='Component name')
    parser_subgraph.add_argument('--parent_depth', type=int, default=1, help='Parent depth (default: 1)')
    parser_subgraph.add_argument('--child_depth', type=int, default=1, help='Child depth (default: 1)')
    
    parser_common_parents = subparsers.add_parser('getCommonParents', help='Get common parents')
    parser_common_parents.add_argument('graph_path', help='Path to graph file')
    parser_common_parents.add_argument('module_name1', help='First module name')
    parser_common_parents.add_argument('component_name1', help='First component name')
    parser_common_parents.add_argument('module_name2', help='Second module name')
    parser_common_parents.add_argument('component_name2', help='Second component name')
    
    parser_common_children = subparsers.add_parser('getCommonChildren', help='Get common children')
    parser_common_children.add_argument('graph_path', help='Path to graph file')
    parser_common_children.add_argument('module_name1', help='First module name')
    parser_common_children.add_argument('component_name1', help='First component name')
    parser_common_children.add_argument('module_name2', help='Second module name')
    parser_common_children.add_argument('component_name2', help='Second component name')
    
    args = parser.parse_args()
    
    if not args.function:
        parser.print_help()
        return
    
    try:
        if args.function == 'getModuleInfo':
            result = getModuleInfo(args.fdep_folder, args.module_name)
            print(json.dumps(result, indent=2))
            
        elif args.function == 'getFunctionInfo':
            result = getFunctionInfo(args.fdep_folder, args.module_name, args.component_name, args.component_type)
            
        elif args.function == 'getFunctionChildren':
            result = getFunctionChildren(args.graph_path, args.module_name, args.component_name, args.depth)
            print(json.dumps(result, indent=2))
            
        elif args.function == 'getFunctionParent':
            result = getFunctionParent(args.graph_path, args.module_name, args.component_name, args.depth)
            print(json.dumps(result, indent=2))
            
        elif args.function == 'getSubgraph':
            result = getSubgraph(
                args.graph_path,
                args.module_name,
                args.component_name,
                args.parent_depth,
                args.child_depth
            )
            # Always print exactly one JSON blob
            if result:
                out = {
                    "nodes": list(result.nodes),
                    "edges": [(u, v) for u, v in result.edges]
                }
            else:
                out = {"nodes": [], "edges": []}
            print(json.dumps(out))
                
        elif args.function == 'getCommonParents':
            result = getCommonParents(args.graph_path, args.module_name1, args.component_name1, 
                                    args.module_name2, args.component_name2)
            print(json.dumps(result, indent=2))
            
        elif args.function == 'getCommonChildren':
            result = getCommonChildren(args.graph_path, args.module_name1, args.component_name1, 
                                     args.module_name2, args.component_name2)
            print(json.dumps(result, indent=2))
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()


#### use cases

# if __name__ == "__main__":
#     fdep_folder = "/Users/suryansh.s/codetraverse/testing/fdep_xyne"
#     graph_path = "/Users/suryansh.s/codetraverse/testing/graph_xyne/repo_function_calls.graphml"
#     module_name = "node_modules/typescript/lib/lib.es5.d"
#     component_name = "NumberFormatOptionsUseGroupingRegistry"
#     module_name1 = "partial.test.ts"
#     componet1 = "string"
#     module_name2 = "partial.test.ts"
#     component2 = "number"
#     module_name3 = "code/node_modules/zod/src/v4/classic/tests/error.test.ts"
#     component3 = "FormattedErrorWithNumber"
#     module_name4 = "code/node_modules/zod/src/v3/tests/error.test.ts"
#     component4 = "FormattedError"
#     component_type = "interface"


#     components = debug_getModuleInfo(fdep_folder, module_name)
#     getFunctionInfo(fdep_folder, module_name, component_name, component_type)

#     module_info = getModuleInfo(fdep_folder, module_name)
#     for info in module_info:
#         print(f"Module: {info.get('module', 'N/A')}, Name: {info.get('name', 'N/A')}, Kind: {info.get('kind', 'N/A')}")

#     children = getFunctionChildren(graph_path, module_name, component_name, depth=100)
#     for child in children:
#         print(f"Child: {child[0]}, Module: {child[1]}, Component: {child[2]}, Depth: {child[3]}")

#     parents_depth = getFunctionParent(graph_path, module_name, component_name, depth=2)
#     for parent in parents_depth:
#         print(f"Parent: {parent[0]}, Module: {parent[1]}, Component: {parent[2]}, Depth: {parent[3]}")

#     sub_graph = getSubgraph(graph_path, module_name, component_name, parent_depth=2, child_depth=2)
#     nx.write_graphml(sub_graph, "subgraph.graphml")

#     common_parents = getCommonParents(graph_path, module_name1, componet1, module_name2, component2)
#     for parent in common_parents:
#         print(f"Common Parent: {parent[0]}, Module: {parent[1]}, Component: {parent[2]}")

#     common_children = getCommonChildren(graph_path, module_name3, component3, module_name4, component4)
#     for child in common_children:
#         print(f"Common Child: {child[0]}, Module: {child[1]}, Component: {child[2]}")