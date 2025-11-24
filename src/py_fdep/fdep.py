import ast
from pathlib import Path
import networkx as nx
from collections import defaultdict
import re

def match_x(s: str, x: str) -> bool:
    if s is None:
        return False
    x_esc = re.escape(x)
    pattern = rf"{x_esc}(?:\..+)?"
    return re.fullmatch(pattern, s) is not None

class ProjectAnalyzer:
    def __init__(self, root_dir):
        self.root = Path(root_dir).resolve()
        self.graph = nx.DiGraph()
        self.file_names = []
        self.import_map = defaultdict(list)
        self.defs = {}

    def collect_defs(self):
        for file in self.root.rglob("*.py"):
            relpath = file.relative_to(self.root)
            self.file_names.append(relpath)
            with open(file, "r", encoding="utf-8") as f:
                src = f.read()

            try:
                tree = ast.parse(src, filename=str(relpath))
            except SyntaxError:
                continue

            self._walk_defs(tree, relpath, src, parent_stack=[])

    def _walk_defs(self, node, relpath, src, parent_stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Build hierarchical name
                parts = parent_stack + [child.name]
                node_id = f"{relpath}::" + "::".join(parts)

                # Extract source code
                start_line = child.lineno - 1
                end_line = child.end_lineno
                lines = src.splitlines()
                extracted = "\n".join(lines[start_line:end_line])

                # Store
                self.defs[node_id] = {
                    "file": str(relpath),
                    "name": child.name,
                    "node": child,
                    "source": extracted
                }

                self._walk_defs(child, relpath, src, parent_stack + [child.name])
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                import_name = child.module if (hasattr(child, "module") and child.module is not None) else child.names[0].name
                # if import_name is None:
                #     print(child.module, child.names[0].name)
                self.import_map[str(relpath)].append(import_name)
                # if str(relpath) == "gnns/pipelines.py":
                #     print(ast.dump(child, indent=4))
            else:
                self._walk_defs(child, relpath, src, parent_stack)

    def build_graph(self):
        for node_id, data in self.defs.items():
            self.graph.add_node(
                node_id,
                file=data["file"],
                name=data["name"],
                source=data["source"]
            )

        name_index = {}
        for node_id, data in self.defs.items():
            name = data["name"]
            name_index.setdefault(name, []).append(node_id)

        for caller_id, data in self.defs.items():
            node = data["node"]
            file_name = data["file"]
            for called_name in self._find_calls(node):
                if called_name not in name_index:
                    continue  # external call

                for callee_id in name_index[called_name]:
                    callee_file = callee_id.split("::")[0]
                    callee_file_import_part = callee_file.split("/")
                    callee_file_import_part[-1] = callee_file_import_part[-1].split(".")[0]
                    caller_imports = self.import_map.get(file_name, [])
                    is_valid_import = (callee_file in caller_imports) | (callee_file == file_name)
                    if not is_valid_import:
                        for callee_part in callee_file_import_part:
                            for called in caller_imports:
                                if match_x(called, callee_part):
                                    is_valid_import = True
                                    break
                    if is_valid_import:
                        self.graph.add_edge(caller_id, callee_id)

        return self.graph

    def _find_calls(self, node):
        calls = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                # foo(...)
                if isinstance(child.func, ast.Name):
                    calls.add(child.func.id)
                # obj.foo(...)
                elif isinstance(child.func, ast.Attribute):
                    calls.add(child.func.attr)
        return calls



def build_project_graph(project_path):
    analyzer = ProjectAnalyzer(project_path)
    analyzer.collect_defs()
    return analyzer.build_graph()
