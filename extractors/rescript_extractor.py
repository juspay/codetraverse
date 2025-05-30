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
        self.source_bytes = b"" # Store source bytes for consistent decoding

    def _get_node_text(self, node: Node) -> str:
        return self.source_bytes[node.start_byte:node.end_byte].decode(errors="ignore")

    def process_file(self, file_path: str):
        with open(file_path, "rb") as f:
            self.source_bytes = f.read()
        
        tree = self.parser.parse(self.source_bytes)
        self.import_map = self._collect_imports(tree.root_node)
        self.all_components = []

        for node in tree.root_node.named_children:
            # Skip imports as they are collected separately
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
            # value_binding is usually inside let_declaration
            # If value_binding can be a top-level node, add it here too.
            # Based on tree-sitter-rescript, let_declaration is more common at top.
        }.get(node.type)

    def _collect_imports(self, root: Node):
        imports = defaultdict(list)
        def walk(n: Node):
            if n.type == "open_statement":
                # ReScript 'open' can be simple 'open Mod' or 'open Mod.Sub'
                # The name is usually in a module_identifier_path or module_identifier
                name_node = n.child_by_field_name("path") # common field name for the module path
                if not name_node: # Fallback to common identifier types
                    name_node = n.child_by_field_name("module") # older grammars might use this
                    if not name_node:
                        for child in n.named_children:
                            if child.type in ("module_identifier", "module_identifier_path"):
                                name_node = child
                                break
                if name_node:
                    module_name = self._get_node_text(name_node)
                    imports[module_name].append({"type": "open", "module": module_name})

            # include_statement is similar to open but copies definitions
            elif n.type == "include_statement":
                name_node = n.child_by_field_name("module") # Or path depending on grammar version
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
        name_node = node.child(1).child(0)
        if not name_node or node.type != "module_declaration":
            return None
        name = self._get_node_text(name_node)
        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        children_components = []
        body_node = node.child_by_field_name("body") # usually 'module_items'
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
            "kind": "module", "name": name,
            "start_line": start, "end_line": end, "code": code,
            "import_map": self.import_map, # Module might have its own import context if supported
            "elements": children_components
        }

    def _extract_type(self, node: Node):
        name_node = node.child_by_field_name("name") # usually 'type_identifier'
        if not name_node: return None
        name = self._get_node_text(name_node)
        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        definition_node = node.child_by_field_name("definition") # or 'body' depending on grammar
        if not definition_node: definition_node = node.child_by_field_name("body")

        variants, fields = [], []
        subkind = "alias_or_abstract" # Default

        if definition_node:
            if definition_node.type == "record_type": # for type t = { field: type }
                subkind = "record"
                for field_decl_node in definition_node.named_children:
                    if field_decl_node.type == "field_declaration":
                        fname_node = field_decl_node.child_by_field_name("name") # usually 'property_identifier'
                        ftype_node = field_decl_node.child_by_field_name("type")
                        if fname_node and ftype_node:
                            fields.append({
                                "name": self._get_node_text(fname_node),
                                "type": self._get_node_text(ftype_node)
                            })
            elif definition_node.type == "variant_type": # for type t = | Variant1 | Variant2(type)
                subkind = "variant"
                for variant_decl_node in definition_node.named_children:
                    if variant_decl_node.type == "variant_constructor_declaration":
                        vname_node = variant_decl_node.child_by_field_name("name") # 'variant_identifier'
                        if not vname_node: continue
                        vname_str = self._get_node_text(vname_node)
                        payloads = []
                        # Parameters for variant constructor are often in 'formal_parameters' or similar
                        params_node = variant_decl_node.child_by_field_name("parameters")
                        if params_node: # This could be a list of types
                             for param_type_node in params_node.named_children: # Iterate over type nodes
                                payloads.append(self._get_node_text(param_type_node))
                        variants.append({"name": vname_str, "payloads": payloads})
            # Could be other kinds like type t = string (alias)
            # The definition_node itself might be a type_identifier for an alias.
            elif definition_node.type == "type_identifier" or definition_node.type == "type_identifier_path":
                subkind = "alias"
                fields.append({"alias_to": self._get_node_text(definition_node)})


        return {
            "kind": "type", "name": name,
            "start_line": start, "end_line": end, "code": code,
            "subkind": subkind, "fields": fields, "variants": variants,
        }

    def _extract_external(self, node: Node):
        name_node = node.child_by_field_name("name") # 'value_identifier'
        if not name_node: return None
        name = self._get_node_text(name_node)
        
        type_node = node.child_by_field_name("type") # 'type_annotation' node
        type_str = self._get_node_text(type_node.named_children[0]) if type_node and type_node.named_children else None
        
        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        return {
            "kind": "external", "name": name,
            "start_line": start, "end_line": end, "type": type_str, "code": code
        }

    def _extract_let_declaration(self, let_decl_node: Node):
        # A let_declaration can have multiple let_bindings, e.g. let a = 1 and b = 2
        components = []
        for binding_node in let_decl_node.named_children:
            if binding_node.type == "let_binding": # Or 'value_binding' if grammar uses that
                component = self._extract_let_binding_details(binding_node)
                if component:
                    components.append(component)
        return components if components else None


    def _extract_let_binding_details(self, node: Node): # Renamed from _extract_value_binding
        pattern_node = node.child_by_field_name("pattern")
        if not pattern_node: return None
        
        # Name can be simple identifier or from a pattern (e.g. in destructuring)
        # For simplicity, taking the text of the whole pattern as name for now.
        name = self._get_node_text(pattern_node) 
        if pattern_node.type == "value_identifier": # More specific name
            name = self._get_node_text(pattern_node)

        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        params, param_annotations = [], {}
        return_type_annotation = None
        is_function = False

        value_node = node.child_by_field_name("value")
        if value_node and value_node.type == "function":
            is_function = True
            # Extract parameters
            parameters_node = value_node.child_by_field_name("parameters") # usually 'formal_parameters'
            if parameters_node:
                for param_child_node in parameters_node.named_children:
                    if param_child_node.type == "parameter":
                        param_name_node = param_child_node.child_by_field_name("pattern") # 'value_identifier'
                        # Also check for labeled_parameter structure
                        if not param_name_node and param_child_node.named_children and param_child_node.named_children[0].type == "labeled_parameter":
                             labeled_node = param_child_node.named_children[0]
                             param_name_node = labeled_node.child_by_field_name("name") # often value_identifier

                        if param_name_node:
                            p_name = self._get_node_text(param_name_node)
                            params.append(p_name)
                            p_type_node = param_child_node.child_by_field_name("type") # 'type_annotation'
                            if p_type_node and p_type_node.named_children:
                                param_annotations[p_name] = self._get_node_text(p_type_node.named_children[0])
            
            # Extract return type annotation from the function node itself
            func_type_ann_node = value_node.child_by_field_name("type") # 'type_annotation' on function
            if func_type_ann_node and func_type_ann_node.named_children:
                return_type_annotation = self._get_node_text(func_type_ann_node.named_children[0])
            
            # The body for walk is the function's body
            fn_body_for_walk = value_node.child_by_field_name("body")
        else:
            # Not a function node, so it's a variable. Body for walk is the value_node itself.
            fn_body_for_walk = value_node

        calls, literals, local_variables, jsx_elements = [], [], [], []

        def walk(n: Node):
            if n.type == "call_expression":
                fn_call_node = n.child_by_field_name("function")
                if fn_call_node:
                    calls.append(self._get_node_text(fn_call_node))
            elif n.type in ("string_literal", "int_literal", "float_literal", "char_literal", "true", "false"): # Adjust based on grammar
                literals.append(self._get_node_text(n))
            elif n.type == "let_binding": # Local let binding
                # Avoid infinite recursion if walk is called on the same top-level node
                if n == node: return 
                local_var_comp = self._extract_let_binding_details(n)
                if local_var_comp: # and local_var_comp["kind"] == "variable":
                    local_variables.append(local_var_comp)
            elif n.type in ("jsx_element", "jsx_self_closing_element"):
                jsx_comp = self._extract_jsx_element(n)
                if jsx_comp:
                    jsx_elements.append(jsx_comp)
            
            # Don't recurse into children of already processed JSX or local let bindings here
            if n.type not in ("jsx_element", "jsx_self_closing_element", "let_binding"):
                for child in n.children:
                    walk(child)

        if fn_body_for_walk:
            walk(fn_body_for_walk)
        
        kind = "function" if is_function else "variable"
        
        result = {
            "kind": kind, "name": name,
            "start_line": start, "end_line": end, "code": code,
            "literals": literals, "function_calls": calls, 
            "local_variables": local_variables, # Renamed from "variables"
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
        # For jsx_element, iterate its children (which are between open and close tags)
        if node.type == "jsx_element":
            # Children nodes are direct children of jsx_element, not open_tag or close_tag
            for child_content_node in node.named_children:
                 if child_content_node.type in ("jsx_element", "jsx_self_closing_element"):
                    children_jsx.append(self._extract_jsx_element(child_content_node))
                 # Could also extract jsx_text or jsx_expression here

        return {
            "kind": "jsx", "tag_name": tag_name,
            "attributes": attributes, "children_jsx": children_jsx,
            "start_line": node.start_point[0] + 1, "end_line": node.end_point[0] + 1,
            "code": self._get_node_text(node)
        }