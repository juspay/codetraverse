# codetraverse/extractors/python_extractor.py

import os
import json
import chardet
from bs4 import BeautifulSoup
from tree_sitter_language_pack import get_parser
import html
from codetraverse.base.component_extractor import ComponentExtractor

def parse_html_to_text(file_path: str) -> str:
    with open(file_path, 'rb') as f:
        raw = f.read()
    guess = chardet.detect(raw)
    encoding = guess['encoding'] or 'utf-8'
    text = raw.decode(encoding, errors='replace')
    soup = BeautifulSoup(text, 'html.parser')
    plain = html.unescape(soup.get_text(separator='\n'))
    return plain

class PythonComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.parser = get_parser("python")
        self.all_components = []

    def parse_file(self, file_path: str):
        plain = parse_html_to_text(file_path)
        tree = self.parser.parse(plain.encode("utf8"))
        return plain, tree

    def get_text(self, node, plain: str) -> str:
        b = plain.encode("utf8")
        return b[node.start_byte:node.end_byte].decode("utf8", errors="replace")

    def extract_decorators(self, node, plain):
        decs = []
        for c in node.children:
            if c.type == "decorator":
                decs.append(self.get_text(c, plain).strip())
        return decs or None

    def extract_parameters(self, node, plain):
        params = []
        for p in node.named_children:
            if p.type == "identifier":
                params.append({"name": self.get_text(p, plain), "annotation": None})
            elif p.type == "typed_parameter":
                name_node = p.child_by_field_name("name")
                type_node = p.child_by_field_name("type")
                name = self.get_text(name_node, plain) if name_node else None
                ann  = self.get_text(type_node, plain) if type_node else None
                params.append({"name": name, "annotation": ann})
        return params or None

    def extract_type_alias(self, node, plain, module_name):
        name_node  = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        return {
            "kind":       "type_alias",
            "module":     module_name,
            "name":       self.get_text(name_node, plain) if name_node else None,
            "annotation": self.get_text(value_node, plain) if value_node else None,
            "start_line": node.start_point[0] + 1,
            "end_line":   node.end_point[0] + 1,
            "code":       self.get_text(node, plain),
        }

    def extract_lambda(self, node, plain, module_name):
        params = None
        pn = node.child_by_field_name("parameters")
        if pn:
            params = self.extract_parameters(pn, plain)
        return {
            "kind":       "lambda",
            "module":     module_name,
            "name":       "<lambda>",
            "parameters": params,
            "start_line": node.start_point[0] + 1,
            "end_line":   node.end_point[0] + 1,
            "code":       self.get_text(node, plain),
        }

    def extract_yield(self, node, plain, module_name):
        return {
            "kind":       "yield",
            "module":     module_name,
            "expression": self.get_text(node, plain),
            "start_line": node.start_point[0] + 1,
            "end_line":   node.end_point[0] + 1,
        }

    # def extract_comprehension(self, node, plain, module_name):
    #     return {
    #         "kind":       node.type,
    #         "module":     module_name,
    #         "code":       self.get_text(node, plain),
    #         "start_line": node.start_point[0] + 1,
    #         "end_line":   node.end_point[0] + 1,
    #     }

    def extract_function_calls(self, node, plain, module_name, rel_path):
        calls = []

        if node.type == "call":
            # grab the dotted or bare name
            fn = node.child_by_field_name("function") or node.children[0]
            if fn:
                full = self.get_text(fn, plain).strip()
                name = full.split("(")[0]

                # ensure we have a project_root to look under
                pr = getattr(self, "project_root", None)
                if pr is None:
                    pr = os.environ.get("ROOT_DIR") or ""

                resolved = None

                # 1) If it was imported via “from X import Y”
                if name in self.imports:
                    mod = self.imports[name]                        # e.g. "codetraverse.utils.networkx_graph"
                    path = mod.replace(".", "/") + ".py"             # → "codetraverse/utils/networkx_graph.py"
                    # absolute on‐disk path
                    abs_path = os.path.join(pr, path)
                    # ** drop the existence check **, or leave it if you want to prefer bare‐mod
                    # if os.path.isfile(abs_path):
                    resolved = f"{path}::{name}"

                # 2) dotted attribute off an import: X.Y.Z
                elif "." in name:
                    root, *rest = name.split(".")
                    leaf = rest[-1]
                    if root in self.imports:
                        mod = self.imports[root]
                        path = mod.replace(".", "/") + ".py"
                        resolved = f"{path}::{leaf}"

                # 3) fallback to local definition
                if not resolved:
                    resolved = f"{rel_path}::{name}"

                calls.append({
                    "name": name,
                    "base_name": name.split(".")[-1],
                    "resolved_callee": resolved
                })

        # recurse
        for c in node.children:
            calls.extend(self.extract_function_calls(c, plain, module_name, rel_path))
        return calls



    def walk_node(self, node, plain, file_path, root_folder, rel_path):
        """
        Recursively walk the Tree-sitter AST and collect component dicts.
        Skips module-level extraction of any function_definition that lives inside a class.
        """
        comps = []
        module_name = os.path.relpath(file_path, root_folder).replace("\\", "/")

        # helper to know if a node is nested inside any class_definition
        def _inside_class(n):
            p = n.parent
            while p:
                if p.type == "class_definition":
                    return True
                p = p.parent
            return False

        # ————————— imports —————————
        if node.type == "import_statement":
            # e.g. `import os, sys as system`
            code = self.get_text(node, plain).strip()
            parts = code.split(None, 1)
            if len(parts) == 2:
                raw = parts[1]
                # split on commas, handle aliases by keeping the full segment
                for name in raw.split(","):
                    name = name.strip()
                    if not name:
                        continue
                    comps.append({
                        "kind": "import",
                        "module": module_name,
                        "name": name,     # now each imported symbol becomes the .name
                        "code": code,
                        "start_line": node.start_point[0] + 1,
                        "end_line":   node.end_point[0] + 1,
                    })

        if node.type == "import_from_statement":
            # e.g. `from typing import NewType, Union as U`
            code = self.get_text(node, plain).strip()
            tokens = code.split()
            if len(tokens) >= 4 and tokens[0] == "from" and tokens[2] == "import":
                source = tokens[1]
                raw = "".join(tokens[3:])  # join back the imported list
                for name in raw.split(","):
                    name = name.strip()
                    if not name:
                        continue
                    comps.append({
                        "kind": "import",
                        "module": module_name,
                        "name": name,
                        "from": source,
                        "code": code,
                        "start_line": node.start_point[0] + 1,
                        "end_line":   node.end_point[0] + 1,
                    })

        # — assignments (module vars) —
        if node.type == "assignment":
            lhs = node.child_by_field_name("left")
            if lhs and lhs.type == "identifier":
                comps.append({
                    "kind": "variable",
                    "module": module_name,
                    "name": self.get_text(lhs, plain),
                    "code": self.get_text(node, plain),
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                })

        # — type aliases —
        if node.type == "type_alias_statement":
            comps.append(self.extract_type_alias(node, plain, module_name))

        # — only module-level function / async definitions (skip those inside a class) —
        if node.type in ("function_definition", "async_function_definition") and not _inside_class(node):
            name_node = node.child_by_field_name("name")
            name = self.get_text(name_node, plain) if name_node else "<anon>"

            # parameters
            params = None
            pn = node.child_by_field_name("parameters")
            if pn:
                params = self.extract_parameters(pn, plain)

            # return annotation
            returns = None
            rt = node.child_by_field_name("return_type")
            if rt:
                returns = self.get_text(rt, plain)

            # decorators and calls
            decs = self.extract_decorators(node, plain)
            calls = self.extract_function_calls(node, plain, module_name, rel_path)

            comps.append({
                "kind": "async_function" if node.type.startswith("async_") else "function",
                "module": module_name,
                "name": name,
                "decorators": decs,
                "parameters": params,
                "returns": returns,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "code": self.get_text(node, plain),
                "function_calls": calls
            })

        # — class definitions + methods —
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            cls_name = self.get_text(name_node, plain) if name_node else "<anon>"
            decs = self.extract_decorators(node, plain)

            # base-classes in parentheses
            bases = []
            bp = node.child_by_field_name("arguments")
            if bp:
                for b in bp.named_children:
                    bases.append(self.get_text(b, plain))

            comps.append({
                "kind": "class",
                "module": module_name,
                "name": cls_name,
                "decorators": decs,
                "bases": bases or None,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "code": self.get_text(node, plain),
            })

            # now pick up its methods
            body = node.child_by_field_name("body")
            if body:
                for m in body.named_children:
                    if m.type in ("function_definition", "async_function_definition"):
                        mn = m.child_by_field_name("name")
                        mname = self.get_text(mn, plain) if mn else "<anon>"

                        mpn = m.child_by_field_name("parameters")
                        mparams = self.extract_parameters(mpn, plain) if mpn else None

                        mdecs = self.extract_decorators(m, plain)
                        mcalls = self.extract_function_calls(m, plain, module_name, rel_path)

                        comps.append({
                            "kind": "async_method" if m.type.startswith("async_") else "method",
                            "module": module_name,
                            "class": cls_name,
                            "name": mname,
                            "decorators": mdecs,
                            "parameters": mparams,
                            "start_line": m.start_point[0] + 1,
                            "end_line": m.end_point[0] + 1,
                            "code": self.get_text(m, plain),
                            "function_calls": mcalls
                        })

        # # — lambdas —
        # if node.type == "lambda":
        #     comps.append(self.extract_lambda(node, plain, module_name))

        # # — yields —
        # if node.type == "yield":
        #     comps.append(self.extract_yield(node, plain, module_name))

        # # — comprehensions —
        # if node.type in (
        #     "list_comprehension",
        #     "set_comprehension",
        #     "dict_comprehension",
        #     "generator_expression"
        # ):
        #     comps.append(self.extract_comprehension(node, plain, module_name))

        # recurse into children
        for c in node.children:
            comps.extend(self.walk_node(c, plain, file_path, root_folder, rel_path))

        return comps


    def extract_from_file(self, filepath, root_folder, rel_path):
        plain, tree = self.parse_file(filepath)
        return self.walk_node(tree.root_node, plain, filepath, root_folder, rel_path)

    def extract_from_folder(self, folder):
        out = []
        project_root = os.environ.get("ROOT_DIR", "")
        abs_folder = os.path.abspath(folder)
        for root, _, files in os.walk(abs_folder):
            for f in files:
                if f.endswith('.py'):
                    file_path = os.path.join(root, f)
                    rel = os.path.relpath(file_path, project_root).replace(os.sep, "/")
                    out.extend(self.extract_from_file(file_path, abs_folder))
        return out

    def process_file(self, file_path: str):
        plain, tree = self.parse_file(file_path)
        root_folder = os.path.dirname(file_path)

        # build import map as you already do…
        self.imports = {}
        root = tree.root_node
        for child in root.children:
            if child.type == "import_statement":
                code = self.get_text(child, plain).strip()
                parts = code.split()
                if parts[0] == "import":
                    for token in " ".join(parts[1:]).split(","):
                        token = token.strip()
                        if " as " in token:
                            mod, alias = token.split(" as ")
                            self.imports[alias.strip()] = mod.strip()
                        else:
                            self.imports[token.split()[0]] = token.split()[0]
            elif child.type == "import_from_statement":
                code = self.get_text(child, plain).strip()
                toks = code.split()
                if toks[0] == "from" and "import" in toks:
                    src = toks[1]
                    names = code.split("import",1)[1].split(",")
                    for n in names:
                        n = n.strip()
                        if " as " in n:
                            orig, alias = n.split(" as ")
                            # map the alias to the module, not to module.func
                            self.imports[alias.strip()] = src
                        else:
                            self.imports[n] = src

                # make project_root available to extract_function_calls
        project_root = os.environ.get("ROOT_DIR", "")
        self.project_root = project_root

        rel = os.path.relpath(file_path, project_root).replace(os.sep, "/")
        # now extract everything
        raw = self.extract_from_file(file_path, root_folder, rel)

        # *** NEW: stamp each comp with a file_path ***
        project_root = os.environ.get("ROOT_DIR", "")
        for c in raw:
            c["file_path"] = rel
            c.setdefault("module", rel)

        # JSON-filter
        self.all_components = [c for c in raw if self._is_jsonable(c)]


    def _is_jsonable(self, x):
        try:
            json.dumps(x)
            return True
        except Exception:
            return False

    def write_to_file(self, output_path: str):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.all_components
