import tree_sitter_python
from tree_sitter import Language, Parser, Node
import json, re
from collections import defaultdict
from base.component_extractor import ComponentExtractor

class PythonComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.PY_LANGUAGE = Language(tree_sitter_python.language())
        self.parser     = Parser(self.PY_LANGUAGE)
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

    def write_to_file(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.all_components


    def _collect_imports(self, root: Node, src: bytes):
        imports = defaultdict(list)
        def walk(n: Node):
            if n.type == "import_statement":
                module = src[n.child(1).start_byte:n.child(1).end_byte]\
                             .decode("utf-8", errors="replace")
                alias = module
                if n.child_by_field_name("alias"):
                    a = n.child_by_field_name("alias")
                    alias = src[a.start_byte:a.end_byte]\
                                .decode("utf-8", errors="replace")
                imports[alias].append(module)

            elif n.type == "import_from_statement":
                mod_node = n.child_by_field_name("module")
                if not mod_node:
                    return
                module = src[mod_node.start_byte:mod_node.end_byte]\
                             .decode("utf-8", errors="replace")
                names = n.child_by_field_name("names")
                if names:
                    for spec in names.named_children:
                        name = src[spec.start_byte:spec.end_byte]\
                                   .decode("utf-8", errors="replace")
                        alias = name
                        if spec.child_by_field_name("alias"):
                            a = spec.child_by_field_name("alias")
                            alias = src[a.start_byte:a.end_byte]\
                                        .decode("utf-8", errors="replace")
                        imports[alias].append(f"{module}.{name}")

            for c in n.children:
                walk(c)

        walk(root)
        return dict(imports)

    def _process_function(self, node: Node, src: bytes):
        name_node  = node.child_by_field_name("name")
        name       = src[name_node.start_byte:name_node.end_byte]\
                         .decode("utf-8", errors="replace")
        start_line = node.start_point[0] + 1
        end_line   = node.end_point[0] + 1
        code       = src[node.start_byte:node.end_byte]\
                         .decode("utf-8", errors="replace")
        params = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for p in params_node.named_children:
                text = src[p.start_byte:p.end_byte]\
                           .decode("utf-8", errors="replace")\
                           .strip()
                params.append(text)
        calls = []
        def walk_calls(n: Node):
            if n.type == "call":
                fn = n.child_by_field_name("function")
                if fn:
                    called = src[fn.start_byte:fn.end_byte]\
                                 .decode("utf-8", errors="replace")
                    calls.append(called)
            for c in n.children:
                walk_calls(c)
        walk_calls(node)
        return {
            "kind":            "function",
            "name":            name,
            "start_line":      start_line,
            "end_line":        end_line,
            "parameters":      params,
            "code":            code,
            "function_calls":  calls,
            "import_map":      self.import_map
        }

    def _process_class(self, node: Node, src: bytes):
        name_node  = node.child_by_field_name("name")
        name       = src[name_node.start_byte:name_node.end_byte]\
                         .decode("utf-8", errors="replace")
        start_line = node.start_point[0] + 1
        end_line   = node.end_point[0] + 1
        code       = src[node.start_byte:node.end_byte]\
                         .decode("utf-8", errors="replace")
        bases = []
        bases_node = node.child_by_field_name("superclasses")
        if bases_node:
            for b in bases_node.named_children:
                bases.append(src[b.start_byte:b.end_byte]\
                                 .decode("utf-8", errors="replace"))
        methods = []
        body = node.child_by_field_name("body")
        if body:
            for stmt in body.named_children:
                if stmt.type == "function_definition":
                    methods.append(self._process_function(stmt, src))
        return {
            "kind":           "class",
            "name":           name,
            "start_line":     start_line,
            "end_line":       end_line,
            "base_classes":   bases,
            "code":           code,
            "methods":        methods,
            "import_map":     self.import_map
        }
