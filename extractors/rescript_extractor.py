import json
import re
import os
from collections import defaultdict
from tree_sitter import Language, Parser, Node
import tree_sitter_rescript
from base.component_extractor import ComponentExtractor

class RescriptComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.RS_LANGUAGE = Language(tree_sitter_rescript.language())
        self.parser = Parser(self.RS_LANGUAGE)
        self.import_map = {}
        self.all_components = []
        self.source_bytes = b""
        self.file_module_name = None

    def _get_node_text(self, node: Node) -> str:
        return self.source_bytes[node.start_byte:node.end_byte].decode(errors="ignore")

    def _find_enclosing_module_name(self, node: Node) -> str:
        cur = node
        while cur is not None:
            if cur.type == "module_declaration":
                for child in cur.named_children:
                    if child.type == "module_binding":
                        for grandchild in child.named_children:
                            if grandchild.type == "module_identifier":
                                module_name = self._get_node_text(grandchild).strip()
                                return module_name
                        break
                break
            cur = cur.parent
        return None

    def process_file(self, file_path: str):
        self.file_module_name = os.path.splitext(os.path.basename(file_path))[0]

        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        self.source_bytes = source_code.encode("utf-8")

        tree = self.parser.parse(self.source_bytes)
        root_node = tree.root_node

        self.import_map = self._collect_imports(root_node)
        self.all_components = []

        def traverse_node(node: Node):
            extractor = self._get_extractor(node)
            if extractor:
                comp_or_list = extractor(node)
                if comp_or_list:
                    if isinstance(comp_or_list, list):
                        for c in comp_or_list:
                            if c:
                                c["file_name"] = self.file_module_name
                                self.all_components.append(c)
                    else:
                        comp_or_list["file_name"] = self.file_module_name
                        self.all_components.append(comp_or_list)

            for child in node.named_children:
                traverse_node(child)

        traverse_node(root_node)

    def extract_function_calls(self, node: Node) -> list:
        function_calls = []

        def traverse_for_calls(n: Node):
            if n.type == 'call_expression':
                fn_node = None
                for child in n.named_children:
                    if child.type in ('value_identifier', 'value_identifier_path', 'member_expression'):
                        fn_node = child
                        break
                if fn_node:
                    txt = self._get_node_text(fn_node).strip()
                    if txt:
                        function_calls.append(txt)

            elif n.type == 'pipe_expression':
                for child in n.named_children:
                    if child.type in ('call_expression', 'value_identifier', 'value_identifier_path'):
                        txt = self._get_node_text(child).strip()
                        if txt:
                            function_calls.append(txt)

            elif n.type == 'value_identifier_path':
                parent = n.parent
                if parent and parent.type in ('call_expression', 'pipe_expression'):
                    txt = self._get_node_text(n).strip()
                    if txt:
                        function_calls.append(txt)

            elif n.type == 'value_identifier':
                parent = n.parent
                if parent and parent.type in ('call_expression', 'pipe_expression'):
                    txt = self._get_node_text(n).strip()
                    if txt:
                        function_calls.append(txt)

            for c in n.children:
                traverse_for_calls(c)

        traverse_for_calls(node)
        seen = set()
        unique = []
        for fn in function_calls:
            if fn not in seen:
                seen.add(fn)
                unique.append(fn)
        return unique

    def extract_literals(self, node: Node) -> list:
        literals = []

        def traverse_for_literals(n: Node):
            if n.type in ('string', 'number', 'true', 'false', 'unit'):
                lit = self._get_node_text(n).strip()
                if lit:
                    literals.append(lit)

            elif n.type in ('string_literal', 'template_literal'):
                lit = self._get_node_text(n).strip()
                if lit:
                    literals.append(lit)

            elif n.type in ('int_literal', 'float_literal'):
                lit = self._get_node_text(n).strip()
                if lit:
                    literals.append(lit)

            elif n.type == 'bool_literal':
                lit = self._get_node_text(n).strip()
                if lit:
                    literals.append(lit)

            elif n.type == 'array':
                arr = self._get_node_text(n).strip()
                if arr:
                    literals.append(arr)

            elif n.type == 'tuple':
                tup = self._get_node_text(n).strip()
                if tup:
                    literals.append(tup)

            elif n.type == 'variant':
                var = self._get_node_text(n).strip()
                if var:
                    literals.append(var)

            elif n.type == 'variant_identifier':
                var = self._get_node_text(n).strip()
                if var:
                    literals.append(var)

            for c in n.children:
                traverse_for_literals(c)

        traverse_for_literals(node)
        seen = set()
        unique = []
        for lit in literals:
            if lit not in seen:
                seen.add(lit)
                unique.append(lit)
        return unique

    def extract_all_components(self):
        return self.all_components

    def write_to_file(self, output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def _get_extractor(self, node: Node):
        return {
            "module_declaration": self._extract_module,
            "type_declaration": self._extract_type,
            "external_declaration": self._extract_external,
            "let_declaration": self._extract_let_declaration,
        }.get(node.type)

    def _collect_imports(self, root: Node):
        imports = defaultdict(list)

        def walk(n: Node):
            if n.type == "open_statement":
                name_node = n.child_by_field_name("path") or n.child_by_field_name("module")
                if not name_node:
                    for c in n.named_children:
                        if c.type in ("module_identifier", "module_identifier_path"):
                            name_node = c
                            break
                if name_node:
                    mname = self._get_node_text(name_node)
                    imports[mname].append({"type": "open", "module": mname})

            elif n.type == "include_statement":
                name_node = n.child_by_field_name("module")
                if not name_node:
                    for c in n.named_children:
                        if c.type in ("module_identifier", "module_identifier_path"):
                            name_node = c
                            break
                if name_node:
                    mname = self._get_node_text(name_node)
                    imports[mname].append({"type": "include", "module": mname})

            for c in n.children:
                walk(c)

        walk(root)
        return dict(imports)

    def _extract_module(self, node: Node):
        name_node = None
        name_node = node.child_by_field_name("name")
        
        if not name_node:
            for i, child in enumerate(node.named_children):
                if child.type == "module_binding":
                    for j, gc in enumerate(child.named_children):
                        if gc.type == "module_identifier":
                            name_node = gc
                            break
                    if name_node:
                        break

        if not name_node:
            return None

        mod_name = self._get_node_text(name_node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = self._get_node_text(node)
        children = []
        for binding in node.named_children:
            if binding.type == "module_binding":
                for block_or_stmt in binding.named_children:
                    if block_or_stmt.type == "block":
                        for stmt in block_or_stmt.named_children:
                            ext = self._get_extractor(stmt)
                            if ext:
                                child_comp = ext(stmt)
                                if child_comp:
                                    if isinstance(child_comp, list):
                                        children.extend(child_comp)
                                    else:
                                        children.append(child_comp)
                    else:
                        ext = self._get_extractor(block_or_stmt)
                        if ext:
                            child_comp = ext(block_or_stmt)
                            if child_comp:
                                if isinstance(child_comp, list):
                                    children.extend(child_comp)
                                else:
                                    children.append(child_comp)

        func_calls = self.extract_function_calls(node)
        lits = self.extract_literals(node)

        comp = {
            "kind": "module",
            "name": mod_name,
            "start_line": start_line,
            "end_line": end_line,
            "code": code,
            "import_map": self.import_map,
            "elements": children,
            "function_calls": func_calls,
            "literals": lits,
        }
        comp["module_name"] = mod_name
        comp["file_name"] = self.file_module_name
        return comp

    def _extract_type(self, node: Node):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        type_name = self._get_node_text(name_node)
        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        definition_node = node.child_by_field_name("definition") or node.child_by_field_name("body")
        variants, fields = [], []
        subkind = "alias_or_abstract"

        if definition_node:
            if definition_node.type == "record_type":
                subkind = "record"
                for field_decl in definition_node.named_children:
                    if field_decl.type == "field_declaration":
                        fn = field_decl.child_by_field_name("name")
                        ft = field_decl.child_by_field_name("type")
                        if fn and ft:
                            fields.append({
                                "name": self._get_node_text(fn),
                                "type": self._get_node_text(ft)
                            })

            elif definition_node.type == "variant_type":
                subkind = "variant"
                for var_decl in definition_node.named_children:
                    if var_decl.type == "variant_constructor_declaration":
                        vname_node = var_decl.child_by_field_name("name")
                        if not vname_node:
                            continue
                        vstr = self._get_node_text(vname_node)
                        payloads = []
                        params_node = var_decl.child_by_field_name("parameters")
                        if params_node:
                            for p in params_node.named_children:
                                payloads.append(self._get_node_text(p))
                        variants.append({"name": vstr, "payloads": payloads})

            elif definition_node.type in ("type_identifier", "type_identifier_path"):
                subkind = "alias"
                fields.append({"alias_to": self._get_node_text(definition_node)})

        func_calls = self.extract_function_calls(node)
        lits = self.extract_literals(node)

        comp = {
            "kind": "type",
            "name": type_name,
            "start_line": start,
            "end_line": end,
            "code": code,
            "subkind": subkind,
            "fields": fields,
            "variants": variants,
            "function_calls": func_calls,
            "literals": lits
        }
        comp["module_name"] = self._find_enclosing_module_name(node)
        comp["file_name"] = self.file_module_name
        return comp

    def _extract_external(self, node: Node):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        ext_name = self._get_node_text(name_node)

        type_node = node.child_by_field_name("type")
        type_str = None
        if type_node and type_node.named_children:
            type_str = self._get_node_text(type_node.named_children[0])

        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        func_calls = self.extract_function_calls(node)
        lits = self.extract_literals(node)

        comp = {
            "kind": "external",
            "name": ext_name,
            "start_line": start,
            "end_line": end,
            "type": type_str,
            "code": code,
            "function_calls": func_calls,
            "literals": lits
        }
        comp["module_name"] = self._find_enclosing_module_name(node)
        comp["file_name"] = self.file_module_name
        return comp

    def _extract_let_declaration(self, let_decl_node: Node):
        components = []
        for binding in let_decl_node.named_children:
            if binding.type == "let_binding":
                c = self._extract_let_binding_details(binding)
                if c:
                    components.append(c)
        return components if components else None

    def is_function(self, node: Node, code: str) -> bool:
        value_node = node.child_by_field_name("value")
        if value_node and value_node.type == "function":
            return True

        equal_pos = code.find('=')
        if equal_pos != -1:
            value_code = code[equal_pos+1:].strip()
            if "=>" in value_code:
                if (
                    re.search(r'=\s*\([^)]*\)\s*=>', code) or
                    re.search(r'=\s*\w+\s*=>', code) or
                    re.match(r'^\([^)]*\)\s*=>', value_code) or
                    re.match(r'^\w+\s*=>', value_code)
                ):
                    return True
        return False

    def _extract_let_binding_details(self, node: Node):
        pattern_node = node.child_by_field_name("pattern")
        if not pattern_node:
            return None
        name = self._get_node_text(pattern_node).strip()

        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        params = []
        param_annotations = {}
        return_type_annotation = None

        value_node = node.child_by_field_name("value")
        is_explicit_fn = value_node and value_node.type == "function"
        fn_body_for_walk = None

        if is_explicit_fn:
            parameters_node = value_node.child_by_field_name("parameters")
            if parameters_node:
                for param_container in parameters_node.named_children:
                    if param_container.type == "parameter":
                        actual = param_container
                        if (param_container.named_children and
                            param_container.named_children[0].type == "labeled_parameter"):
                            actual = param_container.named_children[0]

                        param_name_text = ""
                        cand = actual.child_by_field_name("name")
                        if not cand and actual.type == "parameter":
                            cand = actual.child_by_field_name("pattern")

                        if cand:
                            param_name_text = self._get_node_text(cand).strip()
                        if param_name_text:
                            params.append(param_name_text)
                            param_type_ann = actual.child_by_field_name("type")
                            if param_type_ann and param_type_ann.type == "type_annotation":
                                actual_type_n = param_type_ann.child_by_field_name("type")
                                if actual_type_n:
                                    ttext = self._get_node_text(actual_type_n).strip()
                                    if ttext:
                                        param_annotations[param_name_text] = ttext

            return_type_node = value_node.child_by_field_name("type")
            if return_type_node and return_type_node.type == "type_annotation":
                actual_return = return_type_node.child_by_field_name("type")
                if actual_return:
                    rtext = self._get_node_text(actual_return).strip()
                    if rtext:
                        return_type_annotation = rtext

            fn_body_for_walk = value_node.child_by_field_name("body")
        else:
            fn_body_for_walk = value_node

        calls = self.extract_function_calls(node)
        lits = self.extract_literals(node)

        local_vars, jsx_elems = [], []

        def walk_recursive(cur: Node, depth: int = 0):
            if depth > 50:
                return
            if cur.type == "let_declaration":
                for bind in cur.named_children:
                    if bind.type == "let_binding" and bind != node:
                        lv = self._extract_let_binding_details(bind)
                        if lv:
                            local_vars.append(lv)
                        continue

            elif cur.type == "let_binding" and cur != node:
                lv = self._extract_let_binding_details(cur)
                if lv:
                    local_vars.append(lv)
                return

            elif cur.type in ("jsx_element", "jsx_self_closing_element"):
                jsx_comp = self._extract_jsx_element(cur)
                if jsx_comp:
                    jsx_elems.append(jsx_comp)

            for child in cur.named_children:
                walk_recursive(child, depth+1)

        if fn_body_for_walk:
            walk_recursive(fn_body_for_walk)

        kind = "variable"
        if is_explicit_fn or self.is_function(node, code):
            kind = "function"

        comp = {
            "kind": kind,
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": code,
            "literals": lits,
            "function_calls": calls,
            "local_variables": local_vars,
            "jsx_elements": jsx_elems,
            "import_map": self.import_map
        }
        if kind == "function":
            comp["parameters"] = params
            comp["parameter_type_annotations"] = param_annotations
            comp["return_type_annotation"] = return_type_annotation

        module_name = self._find_enclosing_module_name(node)
        comp["module_name"] = module_name
        comp["file_name"] = self.file_module_name
        return comp

    def _extract_jsx_element(self, node: Node):
        tag_name = "UnknownJSX"
        attributes = []

        if node.type == "jsx_element":
            opening = node.child_by_field_name("open_tag")
            if opening:
                name_node = opening.child_by_field_name("name")
                if name_node:
                    tag_name = self._get_node_text(name_node)
                for attr_node in opening.named_children:
                    if attr_node.type == "jsx_attribute":
                        an = attr_node.child_by_field_name("name")
                        av = attr_node.child_by_field_name("value")
                        a_name = self._get_node_text(an) if an else None
                        a_val  = self._get_node_text(av) if av else None
                        attributes.append({"name": a_name, "value": a_val})

        elif node.type == "jsx_self_closing_element":
            name_node = node.child_by_field_name("name")
            if name_node:
                tag_name = self._get_node_text(name_node)
            for attr_node in node.named_children:
                if attr_node.type == "jsx_attribute": 
                    an = attr_node.child_by_field_name("name")
                    av = attr_node.child_by_field_name("value")
                    a_name = self._get_node_text(an) if an else None
                    a_val  = self._get_node_text(av) if av else None
                    attributes.append({"name": a_name, "value": a_val})

        func_calls = self.extract_function_calls(node)
        lits = self.extract_literals(node)

        comp = {
            "kind": "jsx",
            "tag_name": tag_name,
            "attributes": attributes,
            "function_calls": func_calls,
            "literals": lits
        }
        comp["module_name"] = self._find_enclosing_module_name(node)
        comp["file_name"] = self.file_module_name
        return comp
