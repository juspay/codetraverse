import json
import re
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

    def _get_node_text(self, node: Node) -> str:
        return self.source_bytes[node.start_byte:node.end_byte].decode(errors="ignore")

    def process_file(self, file_path: str):
        with open(file_path, "rb") as f:
            self.source_bytes = f.read()
        
        tree = self.parser.parse(self.source_bytes)
        self.import_map = self._collect_imports(tree.root_node)
        self.all_components = []

        for node in tree.root_node.named_children:
            
            if node.type in ("open_statement", "include_statement"):
                continue
            
            extractor = self._get_extractor(node)
            if extractor:
                component_or_components = extractor(node)
                if component_or_components:
                    if isinstance(component_or_components, list):
                        self.all_components.extend(component_or_components)
                    else:
                        self.all_components.append(component_or_components)

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
                
                
                name_node = n.child_by_field_name("path") 
                if not name_node: 
                    name_node = n.child_by_field_name("module") 
                    if not name_node:
                        for child in n.named_children:
                            if child.type in ("module_identifier", "module_identifier_path"):
                                name_node = child
                                break
                if name_node:
                    module_name = self._get_node_text(name_node)
                    imports[module_name].append({"type": "open", "module": module_name})

            
            elif n.type == "include_statement":
                name_node = n.child_by_field_name("module") 
                if not name_node:
                     for child in n.named_children:
                            if child.type in ("module_identifier", "module_identifier_path"):
                                name_node = child
                                break
                if name_node:
                    module_name = self._get_node_text(name_node)
                    imports[module_name].append({"type": "include", "module": module_name})
            
            for child in n.children:
                walk(child)
        walk(root)
        return dict(imports)

    def _extract_module(self, node: Node):
        """
        Extract a module declaration node safely, handling cases where the AST shape
        doesn’t match exactly the “child(1).child(0)” pattern.
        """
        name_node = node.child_by_field_name("name")

        if not name_node:
            for child in node.named_children:
                if child.type in ("module_identifier", "module_identifier_path"):
                    name_node = child
                    break

        if not name_node:
            return None

        name = self._get_node_text(name_node)

        start_line = node.start_point[0] + 1
        end_line   = node.end_point[0] + 1

        code = self._get_node_text(node)

        children_components = []
        body_node = node.child_by_field_name("body")
        if body_node and body_node.type == "module_items":
            for stmt_node in body_node.named_children:
                extractor = self._get_extractor(stmt_node)
                if extractor:
                    child_comp = extractor(stmt_node)
                    if child_comp:
                        if isinstance(child_comp, list):
                            children_components.extend(child_comp)
                        else:
                            children_components.append(child_comp)

        return {
            "kind": "module",
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "code": code,
            "import_map": self.import_map,
            "elements": children_components
        }


    def _extract_type(self, node: Node):
        name_node = node.child_by_field_name("name") 
        if not name_node: return None
        name = self._get_node_text(name_node)
        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        definition_node = node.child_by_field_name("definition") 
        if not definition_node: definition_node = node.child_by_field_name("body")

        variants, fields = [], []
        subkind = "alias_or_abstract" 

        if definition_node:
            if definition_node.type == "record_type": 
                subkind = "record"
                for field_decl_node in definition_node.named_children:
                    if field_decl_node.type == "field_declaration":
                        fname_node = field_decl_node.child_by_field_name("name") 
                        ftype_node = field_decl_node.child_by_field_name("type")
                        if fname_node and ftype_node:
                            fields.append({
                                "name": self._get_node_text(fname_node),
                                "type": self._get_node_text(ftype_node)
                            })
            elif definition_node.type == "variant_type": 
                subkind = "variant"
                for variant_decl_node in definition_node.named_children:
                    if variant_decl_node.type == "variant_constructor_declaration":
                        vname_node = variant_decl_node.child_by_field_name("name") 
                        if not vname_node: continue
                        vname_str = self._get_node_text(vname_node)
                        payloads = []
                        
                        params_node = variant_decl_node.child_by_field_name("parameters")
                        if params_node: 
                             for param_type_node in params_node.named_children: 
                                payloads.append(self._get_node_text(param_type_node))
                        variants.append({"name": vname_str, "payloads": payloads})
            
            
            elif definition_node.type == "type_identifier" or definition_node.type == "type_identifier_path":
                subkind = "alias"
                fields.append({"alias_to": self._get_node_text(definition_node)})


        return {
            "kind": "type", "name": name,
            "start_line": start, "end_line": end, "code": code,
            "subkind": subkind, "fields": fields, "variants": variants,
        }

    def _extract_external(self, node: Node):
        name_node = node.child_by_field_name("name") 
        if not name_node: return None
        name = self._get_node_text(name_node)
        
        type_node = node.child_by_field_name("type") 
        type_str = self._get_node_text(type_node.named_children[0]) if type_node and type_node.named_children else None
        
        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        return {
            "kind": "external", "name": name,
            "start_line": start, "end_line": end, "type": type_str, "code": code
        }

    def _extract_let_declaration(self, let_decl_node: Node):
        
        components = []
        for binding_node in let_decl_node.named_children:
            if binding_node.type == "let_binding": 
                component = self._extract_let_binding_details(binding_node)
                if component:
                    components.append(component)
        return components if components else None

    def is_function(self, code: str) -> bool:
        passed_equal = False
        for i in range(0, len(code)-1):
            if code[i] == "=" and code[i+1]!=">":
                passed_equal = True
            elif code[i] == "(" or code[i]+code[i+1] == "=>" and passed_equal:
                return True
            elif passed_equal and (code[i] == "{" or code[i].isalnum()):
                return False
        return False

    def _extract_let_binding_details(self, node: Node): 
        pattern_node = node.child_by_field_name("pattern")
        if not pattern_node: return None
        
        
        
        name = self._get_node_text(pattern_node) 
        if pattern_node.type == "value_identifier": 
            name = self._get_node_text(pattern_node)

        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        params, param_annotations = [], {}
        return_type_annotation = None
        is_function = False

        value_node = node.child_by_field_name("value")
        if value_node and value_node.type == "function":
            is_function = True
            
            parameters_node = value_node.child_by_field_name("parameters") 
            if parameters_node:
                for param_child_node in parameters_node.named_children:
                    if param_child_node.type == "parameter":
                        param_name_node = param_child_node.child_by_field_name("pattern") 
                        
                        if not param_name_node and param_child_node.named_children and param_child_node.named_children[0].type == "labeled_parameter":
                             labeled_node = param_child_node.named_children[0]
                             param_name_node = labeled_node.child_by_field_name("name") 

                        if param_name_node:
                            p_name = self._get_node_text(param_name_node)
                            params.append(p_name)
                            p_type_node = param_child_node.child_by_field_name("type") 
                            if p_type_node and p_type_node.named_children:
                                param_annotations[p_name] = self._get_node_text(p_type_node.named_children[0])
            
            
            func_type_ann_node = value_node.child_by_field_name("type") 
            if func_type_ann_node and func_type_ann_node.named_children:
                return_type_annotation = self._get_node_text(func_type_ann_node.named_children[0])
            
            
            fn_body_for_walk = value_node.child_by_field_name("body")
        else:
            
            fn_body_for_walk = value_node

        calls, literals, local_variables, jsx_elements = [], [], [], []

        def walk(n: Node):
            if n.type == "call_expression":
                fn_call_node = n.child_by_field_name("function")
                if fn_call_node:
                    calls.append(self._get_node_text(fn_call_node))
            elif n.type in ("string_literal", "int_literal", "float_literal", "char_literal", "true", "false"): 
                literals.append(self._get_node_text(n))
            elif n.type == "let_binding": 
                
                if n == node: return 
                local_var_comp = self._extract_let_binding_details(n)
                if local_var_comp: 
                    local_variables.append(local_var_comp)
            elif n.type in ("jsx_element", "jsx_self_closing_element"):
                jsx_comp = self._extract_jsx_element(n)
                if jsx_comp:
                    jsx_elements.append(jsx_comp)
            
            
            if n.type not in ("jsx_element", "jsx_self_closing_element", "let_binding"):
                for child in n.children:
                    walk(child)

        if fn_body_for_walk:
            walk(fn_body_for_walk)
        
        kind = "function" if self.is_function(self._get_node_text(node)) else "variable"
        
        result = {
            "kind": kind, "name": name,
            "start_line": start, "end_line": end, "code": code,
            "literals": literals, "function_calls": calls, 
            "local_variables": local_variables, 
            "jsx_elements": jsx_elements,
            "import_map": self.import_map
        }
        if is_function:
            result["parameters"] = params
            result["parameter_type_annotations"] = param_annotations
            result["return_type_annotation"] = return_type_annotation
        
        return result

    def _extract_jsx_element(self, node: Node):
        tag_name = "UnknownJSX"
        attributes = []

        if node.type == "jsx_element":
            opening_element = node.child_by_field_name("open_tag")
            if opening_element:
                name_node = opening_element.child_by_field_name("name")
                if name_node: tag_name = self._get_node_text(name_node)
                for attr_node in opening_element.named_children:
                    if attr_node.type == "jsx_attribute":
                        attr_name_node = attr_node.child_by_field_name("name")
                        attr_value_node = attr_node.child_by_field_name("value")
                        if attr_name_node:
                            attr_name = self._get_node_text(attr_name_node)
                            attr_value = self._get_node_text(attr_value_node) if attr_value_node else "true"
                            attributes.append({"name": attr_name, "value_preview": attr_value[:50]})
        elif node.type == "jsx_self_closing_element":
            name_node = node.child_by_field_name("name")
            if name_node: tag_name = self._get_node_text(name_node)
            for attr_node in node.named_children:
                 if attr_node.type == "jsx_attribute":
                    attr_name_node = attr_node.child_by_field_name("name")
                    attr_value_node = attr_node.child_by_field_name("value")
                    if attr_name_node:
                        attr_name = self._get_node_text(attr_name_node)
                        attr_value = self._get_node_text(attr_value_node) if attr_value_node else "true"
                        attributes.append({"name": attr_name, "value_preview": attr_value[:50]})
        
        children_jsx = []
        
        if node.type == "jsx_element":
            
            for child_content_node in node.named_children:
                 if child_content_node.type in ("jsx_element", "jsx_self_closing_element"):
                    children_jsx.append(self._extract_jsx_element(child_content_node))
                 

        return {
            "kind": "jsx", "tag_name": tag_name,
            "attributes": attributes, "children_jsx": children_jsx,
            "start_line": node.start_point[0] + 1, "end_line": node.end_point[0] + 1,
            "code": self._get_node_text(node)
        }