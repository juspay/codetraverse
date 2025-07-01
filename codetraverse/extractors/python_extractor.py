import tree_sitter_python
from tree_sitter import Language, Parser, Node
import json
from collections import defaultdict
from codetraverse.base.component_extractor import ComponentExtractor

class PythonComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.PY_LANGUAGE = Language(tree_sitter_python.language())
        self.parser = Parser(self.PY_LANGUAGE)
        self.import_map = {}
        self.all_components = []
        self.current_file_path = ""

    def process_file(self, file_path):
        self.current_file_path = file_path
        with open(file_path, "rb") as f:
            src = f.read()
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

    def write_to_file(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.all_components

    def _collect_imports(self, root: Node, src: bytes):
        imports = defaultdict(list)
        def walk(n):
            if n.type == "import_statement":
                module_node = n.child_by_field_name("name")
                if not module_node: return
                
                # Handles multiple dotted names in one import
                for module in module_node.named_children:
                    module_name = src[module.start_byte:module.end_byte].decode()
                    alias_node = module.child_by_field_name("alias")
                    alias = src[alias_node.start_byte:alias_node.end_byte].decode() if alias_node else module_name
                    imports[alias].append(module_name)

            elif n.type == "import_from_statement":
                mod_node = n.child_by_field_name("module_name")
                if not mod_node:
                    return
                module = src[mod_node.start_byte:mod_node.end_byte].decode()
                names_node = n.child_by_field_name("name")
                if names_node:
                    for spec in names_node.named_children:
                        name = src[spec.start_byte:spec.end_byte].decode()
                        alias_node = spec.child_by_field_name("alias")
                        alias = src[alias_node.start_byte:alias_node.end_byte].decode() if alias_node else name
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
                        
        ret_type_node = node.child_by_field_name("return_type")
        ret_type = src[ret_type_node.start_byte:ret_type_node.end_byte].decode() if ret_type_node else None

        calls = []
        literals = []
        variables = []

        def walk(n):
            if n.type == "call":
                fn = n.child_by_field_name("function")
                if fn:
                    called = src[fn.start_byte:fn.end_byte].decode()
                    calls.append(called)
            elif n.type in ("string", "integer", "float"):
                lit = src[n.start_byte:n.end_byte].decode()
                literals.append(lit)
            elif n.type == "assignment":
                ident = n.child_by_field_name("left")
                val = n.child_by_field_name("right")
                if ident and val and ident.type == "identifier":
                    var_name = src[ident.start_byte:ident.end_byte].decode()
                    val_str = src[val.start_byte:val.end_byte].decode()
                    variables.append({ "name": var_name, "value": val_str })
            
            for c in n.children:
                if c.parent.type == "function_definition" and c.type == "assignment":
                    continue
                walk(c)
        
        body_node = node.child_by_field_name("body")
        if body_node:
            walk(body_node)

        return {
            "kind": "function",
            "name": name,
            "file_path": self.current_file_path,
            "start_line": start_line,
            "end_line": end_line,
            "parameters": params,
            "type_annotations": annotations,
            "return_type": ret_type,
            "variables": variables,
            "literals": literals,
            "function_calls": sorted(list(set(calls))),
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
        body_node = node.child_by_field_name("body")
        if body_node:
            for stmt in body_node.named_children:
                if stmt.type == "function_definition":
                    methods.append(self._process_function(stmt, src))
                elif stmt.type == "assignment":
                    ident = stmt.child_by_field_name("left")
                    val = stmt.child_by_field_name("right")
                    if ident and val and ident.type == "identifier":
                        var_name = src[ident.start_byte:ident.end_byte].decode()
                        val_str = src[val.start_byte:val.end_byte].decode()
                        class_vars.append({ "name": var_name, "value": val_str })

        return {
            "kind": "class",
            "name": name,
            "file_path": self.current_file_path,
            "start_line": start_line,
            "end_line": end_line,
            "base_classes": bases,
            "code": code,
            "variables": class_vars,
            "methods": methods,
            "import_map": self.import_map
        }

    def _process_global_assignment(self, node: Node, src: bytes):
        left_node = node.child_by_field_name("left")
        value_node = node.child_by_field_name("right")
        if not left_node or left_node.type != "identifier" or not value_node:
            return None
        
        name = src[left_node.start_byte:left_node.end_byte].decode()
        valuestr = src[value_node.start_byte:value_node.end_byte].decode()
        
        return {
            "kind": "variable",
            "name": name,
            "value": valuestr,
            "file_path": self.current_file_path,
            "location": {
                "start": node.start_point[0] + 1,
                "end": node.end_point[0] + 1
            }
        }