# typescript_extractor.py

import os
import json
from tree_sitter import Language, Parser
import tree_sitter_typescript

from codetraverse.base.component_extractor import ComponentExtractor

class TypeScriptComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.language = Language(tree_sitter_typescript.language_typescript())
        self.parser = Parser(self.language)
        self.components = []
        self.root_folder = os.environ.get("ROOT_DIR")
        if not self.root_folder:
            raise RuntimeError("ROOT_DIR environment variable must be set for TypeScript extractor.")
        self.root_folder = os.path.abspath(self.root_folder)

    def parse_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        tree = self.parser.parse(bytes(code, "utf8"))
        return code, tree
    def set_root_folder(self, root_folder):
        self.root_folder = os.path.abspath(root_folder)


    def get_node_text(self, node, code):
        return code[node.start_byte:node.end_byte]

    def get_relative_path(self, file_path, root_folder):
        rel_path = os.path.relpath(file_path, root_folder).replace("\\", "/")
        return rel_path[:-3] if rel_path.endswith(".ts") else rel_path
    def resolve_imports(self, node, code, current_file_path, root_folder):
        imports = {}
        if node.type == 'import_statement':
            import_text = self.get_node_text(node, code)
            if 'from' in import_text:
                parts = import_text.split('from')
                _, source_path = parts[0], parts[1].strip().strip(";").strip("'\"")
                abs_source = os.path.normpath(os.path.join(os.path.dirname(current_file_path), source_path + ".ts"))
                relative_import_path = self.get_relative_path(abs_source, root_folder)

                # Extract imported names
                if '{' in import_text:
                    names = import_text.split('{')[1].split('}')[0]
                    names = [n.strip() for n in names.split(',')]
                    for name in names:
                        if ' as ' in name:
                            orig, alias = name.split(' as ')
                            imports[alias.strip()] = relative_import_path
                        else:
                            imports[name] = relative_import_path

        # Recurse into children
        for child in node.children:
            imports.update(self.resolve_imports(child, code, current_file_path, root_folder))

        return imports
    def collect_imports_for_file(self, root_node, code, current_file, root_folder):
        imports = {}
        for child in root_node.children:
            if child.type == 'import_statement':
                imports.update(self.resolve_imports(child, code, current_file, root_folder))
        return imports
    def process_file(self, file_path):
        code, tree = self.parse_file(file_path)
        rel_module_path = self.get_relative_path(file_path, self.root_folder)
        imports = self.collect_imports_for_file(tree.root_node, code, file_path, self.root_folder)
        components = self.walk_node(
            tree.root_node, code,
            file_path=file_path,
            root_folder=self.root_folder,
            rel_module_path=rel_module_path,
            imports=imports,
            context={}
        )
        self.components.extend(components)

    
    def write_to_file(self, output_path):
        serializable = []
        for comp in self.components:
            try:
                json.dumps(comp)
                serializable.append(comp)
            except Exception as e:
                print(f"Skipping non-serializable component: {e}")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        
    def extract_all_components(self):
        return self.components
    
    def extract_ident(self, node, code):
        for c in node.children:
            if c.type in ("identifier", "type_identifier", "property_identifier"):
                return self.get_node_text(c, code)
        return None
    
    def walk_node(self, node, code, file_path, root_folder, rel_module_path, imports, context):
        results = []

        # Add per-node extract logic here (function/class/interface/etc.)
        # We'll populate this part in Phase 1.4 onward
        if node.type in ("function_declaration", "function_signature"):
            function_calls = self.extract_function_calls(node, code, rel_module_path, imports)

            fn_name = self.extract_ident(node, code)
            if not fn_name:
                return results  # skip anonymous

            type_sig = self.extract_type_annotation(node, code)
            params = self.extract_parameters(node, code)

            full_path = f"{rel_module_path}::{fn_name}"
            jsdoc = self.extract_jsdoc(node, code)

            results.append({
                "kind": "function",
                "name": fn_name,
                "module": rel_module_path,
                "parameters": params,
                "type_signature": type_sig,
                "function_calls": function_calls,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "full_component_path": full_path,
                "jsdoc": jsdoc,
            })
        
        if node.type in ("class_declaration", "abstract_class_declaration", "class"):
            class_name = self.extract_ident(node, code)
            if not class_name:
                return results
            function_calls = self.extract_function_calls(node, code, rel_module_path, imports, class_name)

            full_class_path = f"{rel_module_path}::{class_name}"
            jsdoc = self.extract_jsdoc(node, code)

            results.append({
                "kind": "class",
                "name": class_name,
                "module": rel_module_path,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "function_calls": function_calls,
                "full_component_path": full_class_path,
                "jsdoc": jsdoc,
            })

            for child in node.children:
                if child.type == "class_body":
                    for member in child.children:
                        # Method
                        if member.type == "method_definition":
                            method_name = self.extract_ident(member, code)
                            if method_name:
                                method_path = f"{rel_module_path}::{class_name}::{method_name}"
                                method_sig = self.extract_type_annotation(member, code)
                                method_params = self.extract_parameters(member, code)
                                results.append({
                                    "kind": "method",
                                    "name": method_name,
                                    "class": class_name,
                                    "module": rel_module_path,
                                    "parameters": method_params,
                                    "type_signature": method_sig,
                                    "start_line": member.start_point[0] + 1,
                                    "end_line": member.end_point[0] + 1,
                                    "full_component_path": method_path,
                                })

                        # Field
                        elif member.type == "public_field_definition":
                            field_name = self.extract_ident(member, code)
                            field_sig = self.extract_type_annotation(member, code)
                            if field_name:
                                results.append({
                                    "kind": "field",
                                    "name": field_name,
                                    "class": class_name,
                                    "module": rel_module_path,
                                    "type_signature": field_sig,
                                    "start_line": member.start_point[0] + 1,
                                    "end_line": member.end_point[0] + 1,
                                    "full_component_path": f"{rel_module_path}::{class_name}::{field_name}",
                                })
        if node.type == "type_alias_declaration":
            type_name = self.extract_ident(node, code)
            if not type_name:
                return results
            function_calls = self.extract_function_calls(node, code, rel_module_path, imports)



            full_path = f"{rel_module_path}::{type_name}"
            jsdoc = self.extract_jsdoc(node, code)

            results.append({
                "kind": "type_alias",
                "name": type_name,
                "module": rel_module_path,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "function_calls": function_calls,
                "full_component_path": full_path,
                "jsdoc": jsdoc,
            })
        if node.type == "interface_declaration":
            iface_name = self.extract_ident(node, code)
            if not iface_name:
                return results

            full_path = f"{rel_module_path}::{iface_name}"
            jsdoc = self.extract_jsdoc(node, code)

            results.append({
                "kind": "interface",
                "name": iface_name,
                "module": rel_module_path,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "full_component_path": full_path,
                "jsdoc": jsdoc,
            })
        if node.type == "enum_declaration":
            enum_name = self.extract_ident(node, code)
            if  enum_name:
                

                full_path = f"{rel_module_path}::{enum_name}"
                jsdoc = self.extract_jsdoc(node, code)

                results.append({
                    "kind": "enum",
                    "name": enum_name,
                    "module": rel_module_path,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "full_component_path": full_path,
                    "jsdoc": jsdoc,
                })
        if node.type == "lexical_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name = self.extract_ident(child, code)
                    if not name:
                        continue

                    value = self.get_node_text(child, code)
                    type_sig = self.extract_type_annotation(child, code)

                    results.append({
                        "kind": "variable",
                        "name": name,
                        "module": rel_module_path,
                        "value": value,
                        "type_signature": type_sig,
                        "start_line": child.start_point[0] + 1,
                        "end_line": child.end_point[0] + 1,
                        "full_component_path": f"{rel_module_path}::{name}",
                    })
        if node.type in ("internal_module", "module"):
            ns_name = self.extract_ident(node, code)
            if not ns_name:
                return results

            full_path = f"{rel_module_path}::{ns_name}"
            jsdoc = self.extract_jsdoc(node, code)

            results.append({
                "kind": "namespace",
                "name": ns_name,
                "module": rel_module_path,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "full_component_path": full_path,
                "jsdoc": jsdoc,
            })
        for child in node.children:
            results.extend(self.walk_node(child, code, file_path, root_folder, rel_module_path, imports, context))

        return results
    def extract_function_calls(self, node, code, rel_module_path, imports, class_name=None):
        calls = []

        def visit(n):
            if n.type == "call_expression":
                fn = n.child_by_field_name("function")
                if fn is None:
                    return

                if fn.type == "identifier":
                    base_name = self.get_node_text(fn, code)
                    callee = imports.get(base_name, rel_module_path)
                    full = f"{callee}::{base_name}"

                    calls.append({
                        "kind": "function_call",
                        "name": base_name,
                        "resolved_callee": full,
                        "full_component_path": full,
                    })

                elif fn.type == "member_expression":
                    obj = fn.child_by_field_name("object")
                    prop = fn.child_by_field_name("property")
                    if obj and prop:
                        obj_name = self.get_node_text(obj, code)
                        prop_name = self.get_node_text(prop, code)
                        if obj.type == "this" and class_name:
                            callee = f"{rel_module_path}::{class_name}::{prop_name}"
                        elif obj.type == "super" and class_name:
                            callee = f"{rel_module_path}::(super_class?)::{prop_name}"
                        else:
                            callee = f"{rel_module_path}::{obj_name}.{prop_name}"

                        calls.append({
                            "kind": "function_call",
                            "name": f"{obj_name}.{prop_name}",
                            "resolved_callee": callee,
                            "full_component_path": callee,
                        })

            for child in getattr(n, 'children', []):
                visit(child)

        visit(node)
        return calls
    def extract_jsdoc(self, node, code):
        if not hasattr(node, "parent") or not node.parent:
            return None
        siblings = node.parent.children
        idx = siblings.index(node)
        for i in range(idx - 1, -1, -1):
            sib = siblings[i]
            if sib.type == "comment":
                comment_text = self.get_node_text(sib, code).strip()
                if comment_text.startswith("/**"):
                    return comment_text
            elif sib.type not in {"comment"}:
                break
        return None
    def extract_type_annotation(self, node, code):
        for child in node.children:
            if child.type == "type_annotation":
                return self.get_node_text(child, code)
            if child.type == "type" and child.children:
                return self.get_node_text(child, code)
        return None
    def extract_parameters(self, node, code):
        params = []
        for c in node.children:
            if c.type == "formal_parameters":
                for param in c.children:
                    if param.type in ("required_parameter", "optional_parameter"):
                        name, typ, default = None, None, None
                        for pc in param.children:
                            if pc.type in ("identifier", "pattern", "type_identifier"):
                                name = self.get_node_text(pc, code)
                            if pc.type == "type_annotation":
                                typ = self.get_node_text(pc, code)
                            if pc.type == "_initializer":
                                default = self.get_node_text(pc, code)
                        params.append({
                            "name": name,
                            "type": typ,
                            "default": default
                        })
        return params


    






                            
        



        # Recurse
        for child in node.children:
            results.extend(self.walk_node(child, code, file_path, root_folder, rel_module_path, imports, context))

        return results


