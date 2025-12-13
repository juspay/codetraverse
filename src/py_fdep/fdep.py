import ast
from pathlib import Path
import networkx as nx
from collections import defaultdict
from typing import Optional
import re

def match_x(s: str, x: str) -> bool:
    if s is None:
        return False
    x_esc = re.escape(x)
    pattern = rf"{x_esc}(?:\..+)?"
    return re.fullmatch(pattern, s) is not None

class ProjectAnalyzer:
    def __init__(self, root_dir, excluded_dirs=None):
        self.root = Path(root_dir).resolve()
        self.graph = nx.DiGraph()
        self.file_names = []
        self.import_map = defaultdict(list)
        self.defs = {}
        if excluded_dirs is None:
            self.excluded_dirs = {'venv', '.venv', 'env', '.env'}
        else:
            self.excluded_dirs = set(excluded_dirs)

    def collect_defs(self):
        for file in self.root.rglob("*.py"):
            if any(part in self.excluded_dirs for part in file.parts):
                continue
            relpath = file.relative_to(self.root)
            self.file_names.append(relpath)
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                src = f.read()

            try:
                tree = ast.parse(src, filename=str(relpath))
            except SyntaxError:
                continue

            self._walk_defs(tree, relpath, src, parent_stack=[])

    def _walk_defs(self, node, relpath, src, parent_stack):
        # Only consider top-level assignments as globals
        is_top_level = len(parent_stack) == 0

        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                parts = parent_stack + [child.name]
                node_id = f"{relpath}::" + "::".join(parts)

                start_line = child.lineno - 1
                end_line = child.end_lineno
                lines = src.splitlines()
                extracted = "\n".join(lines[start_line:end_line])

                node_type = "class" if isinstance(child, ast.ClassDef) else "function"

                self.defs[node_id] = {
                    "file": str(relpath),
                    "name": child.name,
                    "node": child,
                    "code": extracted,
                    "node_type": node_type,
                }

                self._walk_defs(child, relpath, src, parent_stack + [child.name])

            elif is_top_level and isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = []
                if isinstance(child, ast.Assign):
                    targets = child.targets
                else: # AnnAssign
                    targets = [child.target]

                for target in targets:
                    if isinstance(target, ast.Name):
                        node_id = f"{relpath}::{target.id}"
                        start_line = child.lineno - 1
                        end_line = child.end_lineno
                        lines = src.splitlines()
                        extracted = "\n".join(lines[start_line:end_line]) if start_line < end_line else lines[start_line]

                        self.defs[node_id] = {
                            "file": str(relpath),
                            "name": target.id,
                            "node": child,
                            "code": extracted,
                            "node_type": "variable",
                        }

            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                import_name = child.module if (hasattr(child, "module") and child.module is not None) else child.names[0].name
                self.import_map[str(relpath)].append(import_name)

            else:
                self._walk_defs(child, relpath, src, parent_stack)

    def build_graph(self):
        for node_id, data in self.defs.items():
            self.graph.add_node(
                node_id,
                file=data["file"],
                name=data["name"],
                code=data["code"],
                node_type=data.get("node_type", "unknown")
            )

        name_index = {}
        for node_id, data in self.defs.items():
            name = data["name"]
            name_index.setdefault(name, []).append(node_id)

        for caller_id, data in self.defs.items():
            node = data["node"]
            file_name = data["file"]
            for dep_name in self._find_dependencies(node):
                if dep_name not in name_index:
                    continue  # external call or built-in

                # Resolution logic
                possible_callees = name_index[dep_name]
                
                # 1. Prioritize definitions within the same file
                same_file_callees = [cid for cid in possible_callees if self.defs[cid]['file'] == file_name]
                if same_file_callees:
                    for callee_id in same_file_callees:
                        self.graph.add_edge(caller_id, callee_id)
                    continue

                # 2. Check for imported definitions
                caller_imports = self.import_map.get(file_name, [])
                for callee_id in possible_callees:
                    callee_file = self.defs[callee_id]['file']
                    callee_module_path = callee_file.replace('/', '.').replace('.py', '')

                    is_valid_import = False
                    if callee_module_path in caller_imports:
                        is_valid_import = True
                    else:
                        # Handle relative imports and from-imports (e.g. from a.b import c)
                        for imp in caller_imports:
                            if imp and callee_module_path.endswith(imp):
                                is_valid_import = True
                                break
                    
                    if is_valid_import:
                        self.graph.add_edge(caller_id, callee_id)

        return self.graph

    def _find_dependencies(self, node):
        deps = set()
        # We need to skip the name of the function/class itself
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nodes_to_walk = node.body
            # Also consider decorators
            if hasattr(node, 'decorator_list'):
                nodes_to_walk.extend(node.decorator_list)
        else:
            nodes_to_walk = [node]

        for n in nodes_to_walk:
            for child in ast.walk(n):
                # Find function calls
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        deps.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        deps.add(child.func.attr)
                # Find global variable usage
                elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                     deps.add(child.id)
        return deps



def build_project_graph(project_path, graph_output_path: Optional[str]):
    analyzer = ProjectAnalyzer(project_path, excluded_dirs={'venv', '.venv', 'env', '.env'})
    analyzer.collect_defs()
    graph = analyzer.build_graph()
    if graph_output_path:
        nx.write_graphml(graph, graph_output_path)
    return graph
