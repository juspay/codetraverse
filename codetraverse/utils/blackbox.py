import os
import json
from typing import List, Dict, Any
import networkx as nx
from codetraverse.path import load_graph

def getModuleInfo(fdep_folder: str, module_name: str) -> List[Dict[str, Any]]:
    
    def normalize_path(path: str) -> str:
        if not path:
            return ""
        path = os.path.splitext(path)[0]
        return path.replace('\\', '/').strip('/')
    
    def generate_patterns(module_name: str) -> List[str]:
        patterns = [module_name]
        norm = normalize_path(module_name)
        
        if norm != module_name:
            patterns.append(norm)
        
        basename = os.path.basename(norm)
        if basename and basename != norm:
            patterns.append(basename)
        
        # Path variations
        parts = norm.split('/')
        if len(parts) > 1:
            patterns.append('/'.join(parts[-2:]))  # Last 2 parts
            if len(parts) > 2:
                patterns.append('/'.join(parts[-3:]))  # Last 3 parts
        
        return list(dict.fromkeys(patterns))  # Remove duplicates
    
    def matches_pattern(module_path: str, patterns: List[str]) -> bool:
        """Check if module_path matches any pattern."""
        norm_path = normalize_path(module_path)
        
        for pattern in patterns:
            norm_pattern = normalize_path(pattern)
            if (norm_path == norm_pattern or 
                norm_path.endswith(norm_pattern) or 
                norm_pattern.endswith(norm_path) or
                os.path.basename(norm_path) == os.path.basename(norm_pattern)):
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
    
    # Remove duplicates
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

# def getFunctionChildren(graph_path, module_name: str, component_name: str, depth=1) -> List[Dict[str, Any]]:
#     G = load_graph(graph_path)
#     if not G:
#         print(f"❌ Graph not found at {graph_path}")
#         return []
#     target = f"{module_name}::{component_name}"
#     if target not in G:
#         print(f"Error: target '{target}' not in graph.")
#         return []
#     return []

if __name__ == "__main__":
    fdep_folder = "/Users/suryansh.s/codetraverse/fdep_xyne"
    module_name = "webview-ui/src/hooks/useKeyboardShortcuts"
    component_name = "UseKeyboardShortcutsProps"
    component_type = "interface"

    # components = debug_getModuleInfo(fdep_folder, module_name)
    getFunctionInfo(fdep_folder, module_name, component_name, component_type)
    