import tree_sitter_python
from tree_sitter import Language, Parser, Node
import json, re
from collections import defaultdict
from codetraverse.base.component_extractor import ComponentExtractor

class PythonComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.PY_LANGUAGE = Language(tree_sitter_python.language())
        self.parser = Parser(self.PY_LANGUAGE)
        self.import_map = {}
        self.all_components = []

    def process_file(self, file_path):
        src = open(file_path, "rb").read()
        tree = self.parser.parse(src)
        self.import_map = self._collect_imports(tree.root_node, src)
        self.all_components = []

        for node in tree.root_node.named_children:
            if node.type in ("import_statement", "import_from_statement"):
                continue
            if node.type == "function_definition":
                self.all_components.append(self._process_function(node, src))
            elif node.type == "class_definition":
                self.all_components.append(self._process_class(node, src))
            elif node.type == "assignment":
                global_var = self._process_global_assignment(node, src)
                if global_var:
                    self.all_components.append(global_var)
        for comp in self.all_components:
            comp["file_path"] = file_path

    def write_to_file(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.all_components

    def _collect_imports(self, root: Node, src: bytes):
        imports = defaultdict(list)
        def walk(n):
            if n.type == "import_statement":
                module = src[n.child(1).start_byte:n.child(1).end_byte].decode()
                alias = (n.child_by_field_name("alias") and
                         src[n.child_by_field_name("alias").start_byte:
                             n.child_by_field_name("alias").end_byte].decode()) or module
                imports[alias].append(module)
            elif n.type == "import_from_statement":
                mod_node = n.child_by_field_name("module")
                if not mod_node:
                    return
                module = src[mod_node.start_byte:mod_node.end_byte].decode()
                names = n.child_by_field_name("names")
                if names:
                    for spec in names.named_children:
                        name = src[spec.start_byte:spec.end_byte].decode()
                        alias = (spec.child_by_field_name("alias") and
                                 src[spec.child_by_field_name("alias").start_byte:
                                     spec.child_by_field_name("alias").end_byte].decode()) or name
                        imports[alias].append(f"{module}.{name}")
            for c in n.children:
                walk(c)
        walk(root)
        return dict(imports)

    def _process_function(self, node: Node, src: bytes):
        name_node = node.child_by_field_name("name")
        name = src[name_node.start_byte:name_node.end_byte].decode()
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = src[node.start_byte:node.end_byte].decode(errors="ignore")

        # parameters + types
        params = []
        annotations = {}
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for p in params_node.named_children:
                if p.type == "identifier":
                    pname = src[p.start_byte:p.end_byte].decode()
                    params.append(pname)
                elif p.type == "typed_parameter":
                    pname_node = p.child_by_field_name("name")
                    type_node = p.child_by_field_name("type")
                    if pname_node and type_node:
                        pname = src[pname_node.start_byte:pname_node.end_byte].decode()
                        tname = src[type_node.start_byte:type_node.end_byte].decode()
                        params.append(pname)
                        annotations[pname] = tname
                        
        # return type
        ret_type = None
        returns = [c for c in node.children if c.type == "type"]
        if returns:
            ret_type = src[returns[0].start_byte:returns[0].end_byte].decode()

        # extract calls, literals, variables
        calls = []
        literals = []
        variables = []

        def walk(n):
            if n.type == "call":
                fn = n.child_by_field_name("function")
                if fn:
                    called = src[fn.start_byte:fn.end_byte].decode()
                    calls.append(called)
            elif n.type == "string" or n.type == "integer" or n.type == "float":
                lit = src[n.start_byte:n.end_byte].decode()
                literals.append(lit)
            elif n.type == "assignment":
                ident = n.child_by_field_name("left")
                val = n.child_by_field_name("right")
                if ident and val and ident.type == "identifier":
                    name = src[ident.start_byte:ident.end_byte].decode()
                    val_str = src[val.start_byte:val.end_byte].decode()
                    variables.append({ "name": name, "value": val_str })
            for c in n.children:
                walk(c)

        walk(node)

        return {
            "kind": "function",
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "parameters": params,
            "type_annotations": annotations,
            "return_type": ret_type,
            "variables": variables,
            "literals": literals,
            "function_calls": calls,
            "code": code,
            "import_map": self.import_map
        }

    def _process_class(self, node: Node, src: bytes):
        name_node = node.child_by_field_name("name")
        name = src[name_node.start_byte:name_node.end_byte].decode()
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = src[node.start_byte:node.end_byte].decode(errors="ignore")

        bases = []
        bases_node = node.child_by_field_name("superclasses")
        if bases_node:
            for b in bases_node.named_children:
                bases.append(src[b.start_byte:b.end_byte].decode())

        methods = []
        class_vars = []
        for stmt in node.child_by_field_name("body").named_children:
            if stmt.type == "function_definition":
                methods.append(self._process_function(stmt, src))
            elif stmt.type == "assignment":
                ident = stmt.child_by_field_name("left")
                val = stmt.child_by_field_name("right")
                if ident and val and ident.type == "identifier":
                    name = src[ident.start_byte:ident.end_byte].decode()
                    val_str = src[val.start_byte:val.end_byte].decode()
                    class_vars.append({ "name": name, "value": val_str })

        return {
            "kind": "class",
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "base_classes": bases,
            "code": code,
            "variables": class_vars,
            "methods": methods,
            "import_map": self.import_map
        }

    def _process_global_assignment(self, node: Node, src: bytes):
        targets = [c for c in node.children if c.type == "identifier"]
        value_node = node.child_by_field_name("value")
        if not targets or not value_node:
            return None
        valuestr = src[value_node.start_byte:value_node.end_byte].decode()
        for ident in targets:
            name = src[ident.start_byte:ident.end_byte].decode()
            return {
                "kind": "variable",
                "name": name,
                "value": valuestr,
                "location": {
                    "start": node.start_point[0] + 1,
                    "end": node.end_point[0] + 1
                }
            }
