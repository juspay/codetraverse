import os
import re
import tree_sitter_go
from tree_sitter import Language, Parser, Node
import json
from collections import defaultdict
from codetraverse.base.component_extractor import ComponentExtractor

def get_node_text(node, src):
    return src[node.start_byte:node.end_byte].decode(errors="ignore")

def find_first_literal(node):
    queue = [node]
    while queue:
        n = queue.pop(0)
        if n.type in (
            "interpreted_string_literal", "raw_string_literal",
            "int_literal", "float_literal", "rune_literal", "imaginary_literal"
        ):
            return n
        queue.extend(n.children)
    return None

def guess_literal_type(literal_node, src):
    if literal_node is None:
        return None
    t = literal_node.type
    if t in ("interpreted_string_literal", "raw_string_literal"):
        return "string"
    elif t == "int_literal":
        return "int"
    elif t == "float_literal":
        return "float"
    elif t == "rune_literal":
        return "rune"
    elif t == "imaginary_literal":
        return "complex"
    return None
def get_receiver_type(recv_node, src):
    if recv_node is None or len(recv_node.named_children) == 0:
        return None
    type_node = recv_node.named_children[0].child_by_field_name("type")
    if type_node:
        receiver_type = get_node_text(type_node, src).lstrip("*")  
        return receiver_type
    return None

def extract_doc_comment(node, src):
    siblings = node.parent.children if node.parent else []
    idx = siblings.index(node)
    doc = ""
    for i in range(idx-1, -1, -1):
        sib = siblings[i]
        if sib.type == "comment":
            comment_text = get_node_text(sib, src).strip(" /")
            doc = comment_text + "\n" + doc
        else:
            break
    return doc.strip() if doc else None

def find_repo_root(file_path):
    curr = os.path.abspath(file_path)
    while curr != os.path.dirname(curr):
        if os.path.isfile(os.path.join(curr, "go.mod")):
            return curr
        curr = os.path.dirname(curr)
    return None

def get_module_path(go_mod_path):
    with open(go_mod_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("module "):
                return line.split()[1]
    return None

def build_import_path(file_path, repo_root, module_path):
    file_dir = os.path.dirname(os.path.abspath(file_path))
    rel = os.path.relpath(file_dir, repo_root)
    rel = rel.replace(os.sep, "::")
    if rel == ".":
        return module_path
    # Ensure the module_path is not duplicated
    if rel.startswith(module_path):
        return rel
    return f"{module_path}::{rel}"


class GoComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.GO_LANGUAGE = Language(tree_sitter_go.language())
        self.parser = Parser(self.GO_LANGUAGE)
        self.import_map = {}
        self.package_name = ""
        self.all_components = []
        self.method_receivers = defaultdict(list)
        self.comments = []
        self.current_file_path = ""
        self.repo_root = ""
        self.module_path = ""
        self.import_path = ""

    def process_file(self, file_path):
        self.current_file_path = file_path
        repo_root = find_repo_root(file_path)
        if not repo_root:
            raise RuntimeError(f"Couldn't find go.mod for file: {file_path}")
        self.repo_root = repo_root
        self.module_path = get_module_path(os.path.join(repo_root, "go.mod"))
        if not self.module_path:
            raise RuntimeError("Could not parse module path from go.mod")
        self.import_path = build_import_path(file_path, repo_root, self.module_path)

        with open(file_path, "rb") as f:
            src = f.read()
        tree = self.parser.parse(src)
        root = tree.root_node

        # Collect all comments
        self.comments = []
        for node in root.children:
            if node.type == "comment":
                self.comments.append((node.start_point[0] + 1, get_node_text(node, src).strip(" /")))

        # Header docstring
        file_docstring = ""
        for node in root.children:
            if node.type == "comment":
                comment_text = get_node_text(node, src).strip(" /")
                file_docstring += comment_text + "\n"
            elif node.type == "package_clause":
                break

        self.import_map = self._collect_imports(root, src)
        self.package_name = self._collect_package_name(src)

        imports = []
        for node in root.named_children:
            if node.type == "import_declaration":
                for imp in node.named_children:
                    if imp.type == "import_spec_list":
                        for spec in imp.named_children:
                            path_node = spec.child_by_field_name("path")
                            if path_node:
                                pkg = get_node_text(path_node, src).strip('"')
                                imports.append(pkg)
                    elif imp.type == "import_spec":
                        path_node = imp.child_by_field_name("path")
                        if path_node:
                            pkg = get_node_text(path_node, src).strip('"')
                            imports.append(pkg)

        self.all_components = [{
            "kind": "file",
            "file_docstring": file_docstring.strip(),
            "package": self.package_name,
            "module_path": self.module_path,
            "import_path": self.import_path,
            "imports": imports,
            "file_path": os.path.relpath(file_path, start=self.repo_root),  # Use relative path from repo root
        }]
        self.method_receivers = defaultdict(list)

        for node in root.named_children:
            if node.type in ("import_declaration", "package_clause"):
                continue
            elif node.type == "function_declaration":
                func = self._process_function(node, src)
                self.all_components.append(func)
            elif node.type == "method_declaration":
                method = self._process_function(node, src)
                self.all_components.append(method)
                receiver = method.get("receiver_type")
                if receiver:
                    self.method_receivers[receiver].append(method["name"])
            elif node.type == "type_declaration":
                types = self._process_type_declaration(node, src)
                self.all_components.extend(types)
            elif node.type == "var_declaration":
                self.all_components.extend(self._process_var_decl(node, src, global_scope=True))
            elif node.type == "const_declaration":
                self.all_components.extend(self._process_const_decl(node, src))

        # Attach methods to structs
        for comp in self.all_components:
            if comp.get("kind") == "struct":
                struct_name = comp.get("name")
                comp["methods"] = self.method_receivers.get(struct_name, [])

    def write_to_file(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.all_components

    def _collect_package_name(self,src: bytes):
        src_text = src.decode(errors="ignore")
        # print("Source Code:\n", src_text)
        match = re.search(r"^\s*package\s+(\w+)", src_text, re.MULTILINE)
        if match:
            return match.group(1)  
        return "unknown_package"  # Default value if no package name is found

    def _collect_imports(self, root: Node, src: bytes):
        imports = defaultdict(list)
        for node in root.named_children:
            if node.type == "import_declaration":
                for imp in node.named_children:
                    if imp.type == "import_spec_list":
                        for spec in imp.named_children:
                            path_node = spec.child_by_field_name("path")
                            if path_node:
                                module = get_node_text(path_node, src).strip('"')
                                alias_node = spec.child_by_field_name("name")
                                alias = (get_node_text(alias_node, src)
                                         if alias_node else module.split('/')[-1])
                                imports[alias].append(module)
        return dict(imports)

    def _function_complete_path(self, name, receiver_type=None):
        file_path_rel = os.path.relpath(self.current_file_path, start=self.repo_root)
        # Keep file path as-is, don't convert to :: format
        if receiver_type:
            # For methods, combine receiver and method name to maintain module::component format
            return f"{file_path_rel}::{receiver_type}.{name}"
        else:
            return f"{file_path_rel}::{name}"



    def _process_function(self, node: Node, src: bytes):
        kind = "method" if node.type == "method_declaration" else "function"
        receiver_type = None
        if kind == "method":
            recv_node = node.child_by_field_name("receiver")
            if recv_node:
                receiver_type = get_receiver_type(recv_node, src)
        name_node = node.child_by_field_name("name")
        name = get_node_text(name_node, src) if name_node else ""
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = get_node_text(node, src)
        doc = extract_doc_comment(node, src)

        params = []
        param_types = {}
        param_list = node.child_by_field_name("parameters")
        if param_list:
            for p in param_list.named_children:
                names = []
                tname = None
                name_nodes = [c for c in p.children if c.type == "identifier"]
                if name_nodes:
                    names = [get_node_text(n, src) for n in name_nodes]
                type_node = p.child_by_field_name("type")
                if type_node:
                    tname = get_node_text(type_node, src)
                for pname in names:
                    params.append(pname)
                    if tname:
                        param_types[pname] = tname

        ret_type = None
        result_node = node.child_by_field_name("result")
        if result_node:
            ret_type = get_node_text(result_node, src)

        receiver_type = None
        if kind == "method":
            recv_node = node.child_by_field_name("receiver")
            if recv_node:
                receiver_child = [c for c in recv_node.named_children if c.type == "parameter_declaration"]
                if receiver_child:
                    rtype_node = receiver_child[0].child_by_field_name("type")
                    if rtype_node:
                        receiver_type = get_node_text(rtype_node, src).lstrip("*")

        calls, literals, variables, type_deps = [], [], [], set()
        def walk(n):
            if n.type == "call_expression":
                func_node = n.child_by_field_name("function")
                if func_node:
                    callname = get_node_text(func_node, src)
                    calls.append(callname)
            elif n.type in ("interpreted_string_literal", "raw_string_literal",
                            "int_literal", "float_literal", "rune_literal", "imaginary_literal"):
                lit = get_node_text(n, src)
                literals.append(lit)
            elif n.type in ("assignment_statement", "short_var_declaration"):
                left = n.child_by_field_name("left")
                right = n.child_by_field_name("right")
                if left and right:
                    lefts = [c for c in left.named_children if c.type == "identifier"]
                    for ident in lefts:
                        var_name = get_node_text(ident, src)
                        var_val = get_node_text(right, src)
                        variables.append({"name": var_name, "value": var_val})
            elif n.type in ("type_conversion_expression", "qualified_type", "pointer_type"):
                t = get_node_text(n, src)
                type_deps.add(t)
            for c in n.children:
                walk(c)
        body = node.child_by_field_name("body")
        if body:
            walk(body)

        complete_function_path = self._function_complete_path(name, receiver_type if kind == "method" else None)

        out = {
            "kind": kind,
            "name": name,
            "module": os.path.relpath(self.current_file_path, start=self.repo_root),  # Add module field for getModuleInfo compatibility
            "complete_function_path": complete_function_path,
            "start_line": start_line,
            "end_line": end_line,
            "doc_comment": doc,
            "parameters": params,
            "parameter_types": param_types,
            "return_type": ret_type,
            "receiver_type": receiver_type,
            "variables": variables,
            "literals": literals,
            "function_calls": calls,
            "type_dependencies": list(type_deps),
            "code": code,
            "import_map": self.import_map,
            "package": self.package_name,
            "import_path": self.import_path,
            "module_path": self.module_path,
            "file_path": os.path.relpath(self.current_file_path, start=self.repo_root),  # Use relative path from repo root

        }
        return out


    def _process_type_declaration(self, node: Node, src: bytes):
        types = []
        for spec in node.named_children:
            name_node = spec.child_by_field_name("name")
            type_node = spec.child_by_field_name("type")
            type_params_node = spec.child_by_field_name("type_parameters")
            if not name_node or not type_node:
                continue
            tname = get_node_text(name_node, src)
            start_line = spec.start_point[0] + 1
            end_line = spec.end_point[0] + 1
            code = get_node_text(spec, src)
            doc = extract_doc_comment(spec, src)
            type_kind = type_node.type
            if type_kind == "struct_type":
                fields = []
                field_types = set()
                field_list = type_node.child_by_field_name("body")
                if field_list:
                    for fld in field_list.named_children:
                        if fld.type == "field_declaration":
                            field_names = [get_node_text(n, src)
                                           for n in fld.children if n.type in ("identifier", "field_identifier")]
                            field_type_node = fld.child_by_field_name("type")
                            field_type = get_node_text(field_type_node, src) if field_type_node else None
                            tag = None
                            tag_node = None
                            for n in fld.named_children:
                                if n.type == "tag":
                                    tag_node = n
                                    tag = get_node_text(tag_node, src)
                            if not field_names and field_type:
                                fields.append({"name": None, "type": field_type, "tag": tag})
                                field_types.add(field_type)
                            for fname in field_names:
                                fields.append({"name": fname, "type": field_type, "tag": tag})
                                if field_type:
                                    field_types.add(field_type)
                types.append({
                    "kind": "struct",
                    "name": tname,
                    "module": os.path.relpath(self.current_file_path, start=self.repo_root),  # Add module field for getModuleInfo compatibility
                    "start_line": start_line,
                    "end_line": end_line,
                    "doc_comment": doc,
                    "fields": fields,
                    "field_types": list(field_types),
                    "methods": [],
                    "type_parameters": self._extract_type_params(type_params_node, src),
                    "code": code,
                    "import_map": self.import_map,
                    "package": self.package_name,
                    "file_path": os.path.relpath(self.current_file_path, start=self.repo_root),

                })
            elif type_kind == "interface_type":
                methods = []
                type_deps = set()
                iface_body = type_node.child_by_field_name("body")
                if iface_body:
                    for elem in iface_body.named_children:
                        if elem.type == "method_elem":
                            mname_node = elem.child_by_field_name("name")
                            mname = get_node_text(mname_node, src) if mname_node else None
                            params, param_types = self._extract_params_and_types(elem.child_by_field_name("parameters"), src)
                            ret_type = None
                            result_node = elem.child_by_field_name("result")
                            if result_node:
                                ret_type = get_node_text(result_node, src)
                                type_deps.add(ret_type)
                            methods.append({
                                "name": mname,
                                "parameters": params,
                                "parameter_types": param_types,
                                "return_type": ret_type,
                            })
                        elif elem.type == "type_elem":
                            type_str = get_node_text(elem, src)
                            type_deps.add(type_str)
                types.append({
                    "kind": "interface",
                    "name": tname,
                    "module": os.path.relpath(self.current_file_path, start=self.repo_root),  # Add module field for getModuleInfo compatibility
                    "start_line": start_line,
                    "end_line": end_line,
                    "doc_comment": doc,
                    "methods": methods,
                    "type_dependencies": list(type_deps),
                    "type_parameters": self._extract_type_params(type_params_node, src),
                    "code": code,
                    "import_map": self.import_map,
                    "package": self.package_name,
                    "file_path": os.path.relpath(self.current_file_path, start=self.repo_root),

                })
            elif type_kind == "qualified_type":
                aliased_type = get_node_text(type_node, src)
                types.append({
                    "kind": "type_alias",
                    "name": tname,
                    "module": os.path.relpath(self.current_file_path, start=self.repo_root),  # Add module field for getModuleInfo compatibility
                    "aliased_type": aliased_type,
                    "start_line": start_line,
                    "end_line": end_line,
                    "doc_comment": doc,
                    "code": code,
                    "import_map": self.import_map,
                    "package": self.package_name,
                    "file_path": os.path.relpath(self.current_file_path, start=self.repo_root),

                })
            else:
                aliased_type = get_node_text(type_node, src)
                types.append({
                    "kind": "type_alias",
                    "name": tname,
                    "module": os.path.relpath(self.current_file_path, start=self.repo_root),  # Add module field for getModuleInfo compatibility
                    "aliased_type": aliased_type,
                    "start_line": start_line,
                    "end_line": end_line,
                    "doc_comment": doc,
                    "code": code,
                    "import_map": self.import_map,
                    "package": self.package_name,
                    "file_path": os.path.relpath(self.current_file_path, start=self.repo_root),

                })
        return types

    def _extract_type_params(self, node, src):
        if not node:
            return []
        names = []
        for child in node.named_children:
            if child.type == "type_parameter_declaration":
                for n in child.named_children:
                    if n.type == "identifier":
                        names.append(get_node_text(n, src))
        return names

    def _extract_params_and_types(self, param_list, src):
        params = []
        param_types = {}
        if param_list:
            for p in param_list.named_children:
                names = []
                tname = None
                name_nodes = [c for c in p.children if c.type == "identifier"]
                if name_nodes:
                    names = [get_node_text(n, src) for n in name_nodes]
                type_node = p.child_by_field_name("type")
                if type_node:
                    tname = get_node_text(type_node, src)
                for pname in names:
                    params.append(pname)
                    if tname:
                        param_types[pname] = tname
        return params, param_types

    def _process_var_decl(self, node: Node, src: bytes, global_scope=False):
        vars_ = []
        for spec in node.named_children:
            doc = extract_doc_comment(spec, src)
            for child in spec.named_children:
                if child.type == "identifier":
                    name = get_node_text(child, src)
                    value_node = None
                    type_node = None
                    for ch in spec.named_children:
                        if ch.type == "type":
                            type_node = ch
                        elif ch.type not in ("identifier", "type"):
                            value_node = ch
                    value = get_node_text(value_node, src) if value_node else None

                    # Find the literal and guess type if type is not explicit
                    literal_node = None
                    if value_node:
                        literal_node = find_first_literal(value_node)
                    if type_node:
                        type_str = get_node_text(type_node, src)
                    elif literal_node:
                        type_str = guess_literal_type(literal_node, src)
                    else:
                        type_str = None
                    vars_.append({
                        "kind": "variable",
                        "name": name,
                        "module": os.path.relpath(self.current_file_path, start=self.repo_root),  # Add module field for getModuleInfo compatibility
                        "type": type_str,
                        "value": value,
                        "doc_comment": doc,
                        "location": {
                            "start": node.start_point[0] + 1,
                            "end": node.end_point[0] + 1,
                        },
                        "scope": "global" if global_scope else "local",
                        "file_path": os.path.relpath(self.current_file_path, start=self.repo_root),

                    })
        return vars_

    def _process_const_decl(self, node: Node, src: bytes):
        consts_ = []
        for spec in node.named_children:
            doc = extract_doc_comment(spec, src)
            for child in spec.named_children:
                if child.type == "identifier":
                    name = get_node_text(child, src)
                    value_node = None
                    type_node = None
                    for ch in spec.named_children:
                        if ch.type == "type":
                            type_node = ch
                        elif ch.type not in ("identifier", "type"):
                            value_node = ch
                    value = get_node_text(value_node, src) if value_node else None

                    # Find the literal and guess type if type is not explicit
                    literal_node = None
                    if value_node:
                        literal_node = find_first_literal(value_node)
                    if type_node:
                        type_str = get_node_text(type_node, src)
                    elif literal_node:
                        type_str = guess_literal_type(literal_node, src)
                    else:
                        type_str = None
                    consts_.append({
                        "kind": "constant",
                        "name": name,
                        "module": os.path.relpath(self.current_file_path, start=self.repo_root),  # Add module field for getModuleInfo compatibility
                        "type": type_str,
                        "value": value,
                        "doc_comment": doc,
                        "location": {
                            "start": node.start_point[0] + 1,
                            "end": node.end_point[0] + 1,
                        },
                        "file_path": os.path.relpath(self.current_file_path, start=self.repo_root),

                    })
        return consts_

