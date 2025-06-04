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
        """Process a ReScript file and extract all components"""
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        self.source_bytes = bytes(source_code, 'utf8')
        tree = self.parser.parse(self.source_bytes)
        root_node = tree.root_node
        
        # Collect imports first
        self.import_map = self._collect_imports(root_node)
        
        # Extract all components
        self.all_components = []
        
        def traverse_node(node):
            extractor = self._get_extractor(node)
            if extractor:
                component = extractor(node)
                if component:
                    if isinstance(component, list):
                        for comp in component:
                            if comp:
                                self.all_components.append(comp)
                    else:
                        self.all_components.append(component)
            
            # Continue traversing children
            for child in node.named_children:
                traverse_node(child)
        
        traverse_node(root_node)

    def extract_function_calls(self, node: Node) -> list:
        """Extract all function calls from a node and its children"""
        function_calls = []
        
        def traverse_for_calls(n: Node):
            # Handle different types of call expressions
            if n.type == 'call_expression':
                # Get the function being called
                function_node = None
                for child in n.named_children:
                    if child.type in ['value_identifier', 'value_identifier_path', 'member_expression']:
                        function_node = child
                        break
                
                if function_node:
                    call_name = self._get_node_text(function_node)
                    if call_name and call_name.strip():
                        function_calls.append(call_name.strip())
            
            # Handle pipe expressions (|>)
            elif n.type == 'pipe_expression':
                # In pipe expressions, the right side is often a function call
                for child in n.named_children:
                    if child.type in ['call_expression', 'value_identifier', 'value_identifier_path']:
                        call_name = self._get_node_text(child)
                        if call_name and call_name.strip():
                            function_calls.append(call_name.strip())
            
            # Handle member expressions (Module.function)
            elif n.type == 'value_identifier_path':
                # Check if this is being called
                parent = n.parent
                if parent and parent.type in ['call_expression', 'pipe_expression']:
                    call_name = self._get_node_text(n)
                    if call_name and call_name.strip():
                        function_calls.append(call_name.strip())
            
            # Handle simple identifiers that might be function calls
            elif n.type == 'value_identifier':
                parent = n.parent
                if parent and parent.type in ['call_expression', 'pipe_expression']:
                    call_name = self._get_node_text(n)
                    if call_name and call_name.strip():
                        function_calls.append(call_name.strip())
            
            # Recursively check children
            for child in n.children:
                traverse_for_calls(child)
        
        traverse_for_calls(node)
        # Remove duplicates while preserving order
        seen = set()
        unique_calls = []
        for call in function_calls:
            if call not in seen:
                seen.add(call)
                unique_calls.append(call)
        
        return unique_calls
    
    def extract_literals(self, node: Node) -> list:
        """Extract all literals from a node and its children"""
        literals = []
        
        def traverse_for_literals(n: Node):
            # Handle basic literals
            if n.type in ['string', 'number', 'true', 'false', 'unit']:
                literal_value = self._get_node_text(n)
                if literal_value and literal_value.strip():
                    literals.append(literal_value.strip())
            
            # Handle string literals with different names
            elif n.type in ['string_literal', 'template_literal']:
                literal_value = self._get_node_text(n)
                if literal_value and literal_value.strip():
                    literals.append(literal_value.strip())
            
            # Handle numeric literals
            elif n.type in ['int_literal', 'float_literal']:
                literal_value = self._get_node_text(n)
                if literal_value and literal_value.strip():
                    literals.append(literal_value.strip())
            
            # Handle boolean literals
            elif n.type in ['bool_literal']:
                literal_value = self._get_node_text(n)
                if literal_value and literal_value.strip():
                    literals.append(literal_value.strip())
            
            # Handle array literals
            elif n.type == 'array':
                array_content = self._get_node_text(n)
                if array_content and array_content.strip():
                    literals.append(array_content.strip())
            
            # Handle tuple literals
            elif n.type == 'tuple':
                tuple_content = self._get_node_text(n)
                if tuple_content and tuple_content.strip():
                    literals.append(tuple_content.strip())
            
            # Handle variant literals
            elif n.type == 'variant':
                variant_content = self._get_node_text(n)
                if variant_content and variant_content.strip():
                    literals.append(variant_content.strip())
            
            # Handle variant identifiers
            elif n.type == 'variant_identifier':
                variant_content = self._get_node_text(n)
                if variant_content and variant_content.strip():
                    literals.append(variant_content.strip())
            
            # Recursively check children
            for child in n.children:
                traverse_for_literals(child)
        
        traverse_for_literals(node)
        # Remove duplicates while preserving order
        seen = set()
        unique_literals = []
        for literal in literals:
            if literal not in seen:
                seen.add(literal)
                unique_literals.append(literal)
        
        return unique_literals

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
        end_line = node.end_point[0] + 1
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

        # Extract function calls and literals for the module
        function_calls = self.extract_function_calls(node)
        literals = self.extract_literals(node)

        return {
            "kind": "module",
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "code": code,
            "import_map": self.import_map,
            "elements": children_components,
            "function_calls": function_calls,
            "literals": literals
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

        # Extract function calls and literals for the type
        function_calls = self.extract_function_calls(node)
        literals = self.extract_literals(node)

        return {
            "kind": "type", "name": name,
            "start_line": start, "end_line": end, "code": code,
            "subkind": subkind, "fields": fields, "variants": variants,
            "function_calls": function_calls,
            "literals": literals
        }

    def _extract_external(self, node: Node):
        name_node = node.child_by_field_name("name") 
        if not name_node: return None
        name = self._get_node_text(name_node)
        
        type_node = node.child_by_field_name("type") 
        type_str = self._get_node_text(type_node.named_children[0]) if type_node and type_node.named_children else None
        
        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        code = self._get_node_text(node)

        # Extract function calls and literals for the external declaration
        function_calls = self.extract_function_calls(node)
        literals = self.extract_literals(node)

        return {
            "kind": "external", "name": name,
            "start_line": start, "end_line": end, "type": type_str, "code": code,
            "function_calls": function_calls,
            "literals": literals
        }

    def _extract_let_declaration(self, let_decl_node: Node):
        components = []
        for binding_node in let_decl_node.named_children:
            if binding_node.type == "let_binding": 
                component = self._extract_let_binding_details(binding_node)
                if component:
                    components.append(component)
        return components if components else None

    def is_function(self, node: Node, code: str) -> bool:
        """
        Improved function detection using AST structure and code analysis
        """
        # Check if the value node is explicitly a function
        value_node = node.child_by_field_name("value")
        if value_node and value_node.type == "function":
            return True
        
        # Check for arrow functions in the code
        if "=>" in code:
            return True
            
        # Check for function patterns with parameters
        if re.search(r'=\s*\([^)]*\)\s*=>', code):
            return True
            
        # Check for curried function patterns
        if re.search(r'=\s*\w+\s*=>', code):
            return True
            
        # Check if it has function call patterns that suggest it's a function
        # This is more conservative - only if we see clear function patterns
        equal_pos = code.find('=')
        if equal_pos != -1:
            after_equal = code[equal_pos+1:].strip()
            # Check for common function patterns
            if (after_equal.startswith('(') or 
                re.match(r'^\w+\s*=>', after_equal) or
                re.match(r'^\([^)]*\)\s*=>', after_equal)):
                return True
        
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
        is_function_node = False

        value_node = node.child_by_field_name("value")
        if value_node and value_node.type == "function":
            is_function_node = True
            
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

        # Extract function calls and literals using the new methods
        calls = self.extract_function_calls(node)
        literals = self.extract_literals(node)
        
        local_variables, jsx_elements = [], []

        def walk(n: Node):
            if n.type == "let_binding": 
                if n == node: return  # Skip self
                local_var_comp = self._extract_let_binding_details(n)
                if local_var_comp: 
                    local_variables.append(local_var_comp)
            
            elif n.type in ("jsx_element", "jsx_self_closing_element"):
                jsx_comp = self._extract_jsx_element(n)
                if jsx_comp:
                    jsx_elements.append(jsx_comp)
            
            # Continue walking for most node types
            if n.type not in ("jsx_element", "jsx_self_closing_element", "let_binding"):
                for child in n.children:
                    walk(child)

        if fn_body_for_walk:
            walk(fn_body_for_walk)
        
        # Use improved function detection
        kind = "function" if self.is_function(node, code) else "variable"
        
        result = {
            "kind": kind, "name": name,
            "start_line": start, "end_line": end, "code": code,
            "literals": literals, "function_calls": calls, 
            "local_variables": local_variables, 
            "jsx_elements": jsx_elements,
            "import_map": self.import_map
        }
        
        if is_function_node or kind == "function":
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
                if name_node:
                    tag_name = self._get_node_text(name_node)
                for attr_node in opening_element.named_children:
                    if attr_node.type == "jsx_attribute":
                        attr_name_node = attr_node.child_by_field_name("name")
                        attr_value_node = attr_node.child_by_field_name("value")
                        attr_name = self._get_node_text(attr_name_node) if attr_name_node else None
                        attr_value = self._get_node_text(attr_value_node) if attr_value_node else None
                        attributes.append({"name": attr_name, "value": attr_value})

        elif node.type == "jsx_self_closing_element":
            name_node = node.child_by_field_name("name")
            if name_node:
                tag_name = self._get_node_text(name_node)
            for attr_node in node.named_children:
                if attr_node.type == "jsx_attribute":
                    attr_name_node = attr_node.child_by_field_name("name")
                    attr_value_node = attr_node.child_by_field_name("value")
                    attr_name = self._get_node_text(attr_name_node) if attr_name_node else None
                    attr_value = self._get_node_text(attr_value_node) if attr_value_node else None
                    attributes.append({"name": attr_name, "value": attr_value})

        # Extract function calls and literals from JSX element
        function_calls = self.extract_function_calls(node)
        literals = self.extract_literals(node)

        return {
            "kind": "jsx",
            "tag_name": tag_name,
            "attributes": attributes,
            "function_calls": function_calls,
            "literals": literals
        }