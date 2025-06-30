import tree_sitter_rust
from tree_sitter import Language, Parser, Node
import json, re
from collections import defaultdict
from codetraverse.base.component_extractor import ComponentExtractor

class RustComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.RS_LANGUAGE = Language(tree_sitter_rust.language())
        self.parser = Parser(self.RS_LANGUAGE)
        self.raw_components = []
        self.import_mappings = {} 
        self.wildcard_imports = []
        self.current_file_path = ""
        self.current_module_path = ""
        self.module_stack = []

    def process_file(self, file_path: str):
        src = open(file_path, "rb").read()
        tree = self.parser.parse(src)
        self.raw_components = []
        self.import_mappings = {}
        self.wildcard_imports = []
        self.current_file_path = file_path
        self.current_module_path = self._get_module_path_from_file(file_path)
        self.module_stack = [self.current_module_path]
        self._collect_imports(tree.root_node, src)
        for node in tree.root_node.named_children:
            comp = self._process_node(node, src, file_path)
            if comp:
                self.raw_components.append(comp)

    def _get_module_path_from_file(self, file_path: str) -> str:
        import os
        file_path = file_path.replace('\\', '/')
        path_without_ext = os.path.splitext(file_path)[0]
        parts = path_without_ext.split('/')
        src_index = -1
        for i, part in enumerate(parts):
            if part == 'src':
                src_index = i
                break
        if src_index == -1:
            return f"crate::{os.path.basename(path_without_ext)}"
        module_parts = parts[src_index + 1:]
        if not module_parts:
            return "crate"
        if len(module_parts) == 1:
            if module_parts[0] in ['main', 'lib']:
                return "crate"
            else:
                return f"crate::{module_parts[0]}"
        if module_parts[-1] == 'mod':
            module_parts = module_parts[:-1]
        if not module_parts:
            return "crate"
        return "crate::" + "::".join(module_parts)

    def _collect_imports(self, root_node: Node, src: bytes):
        def walk_for_imports(node: Node):
            if node.type == 'use_declaration':
                self._process_use_declaration_for_mapping(node, src)
            for child in node.named_children:
                walk_for_imports(child)
        walk_for_imports(root_node)

    def _process_use_declaration_for_mapping(self, node: Node, src: bytes):
        arg_node = node.child_by_field_name('argument')
        if arg_node:
            self._extract_import_mappings(arg_node, src, "")

    def _extract_import_mappings(self, node: Node, src: bytes, base_path: str):
        if node.type == 'identifier':
            symbol = src[node.start_byte:node.end_byte].decode('utf8')
            full_path = f"{base_path}::{symbol}" if base_path else symbol
            self.import_mappings[symbol] = full_path
        elif node.type == 'scoped_identifier':
            path_node = node.child_by_field_name('path')
            name_node = node.child_by_field_name('name')
            if path_node and name_node:
                path_str = src[path_node.start_byte:path_node.end_byte].decode('utf8')
                name_str = src[name_node.start_byte:name_node.end_byte].decode('utf8')
                full_path = f"{base_path}::{path_str}::{name_str}" if base_path else f"{path_str}::{name_str}"
                self.import_mappings[name_str] = full_path
        elif node.type == 'scoped_use_list':
            path_node = node.child_by_field_name('path')
            list_node = node.child_by_field_name('list')
            if path_node and list_node:
                path_str = src[path_node.start_byte:path_node.end_byte].decode('utf8')
                current_base = f"{base_path}::{path_str}" if base_path else path_str
                for child in list_node.named_children:
                    self._extract_import_mappings(child, src, current_base)
        elif node.type == 'use_list':
            for child in node.named_children:
                self._extract_import_mappings(child, src, base_path)
        elif node.type == 'use_wildcard':
            if base_path:
                self.wildcard_imports.append(base_path)
        elif node.type == 'crate':
            return "crate"

    def _resolve_symbol_path(self, symbol_path: str) -> str:
        parts = symbol_path.split("::")
        if not parts:
            return symbol_path
        first_symbol = parts[0].strip()
        if first_symbol in self.import_mappings:
            full_first_part = self.import_mappings[first_symbol]
            if len(parts) == 1:
                return full_first_part
            else:
                remaining_parts = "::".join(parts[1:])
                return f"{full_first_part}::{remaining_parts}"
        return symbol_path

    def write_to_file(self, output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.raw_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.raw_components

    def _extract_type_info(self, node: Node, src: bytes) -> str:
        if not node:
            return None
        type_text = src[node.start_byte:node.end_byte].decode('utf8')
        if node.type == 'generic_type':
            base_type = node.child_by_field_name('type')
            type_args = node.child_by_field_name('type_arguments')
            base_text = src[base_type.start_byte:base_type.end_byte].decode('utf8') if base_type else ''
            args_text = src[type_args.start_byte:type_args.end_byte].decode('utf8') if type_args else ''
            return f"{base_text}{args_text}"
        return type_text

    def _extract_visibility(self, node: Node, src: bytes) -> str:
        for child in node.children:
            if child.type == 'visibility_modifier':
                return src[child.start_byte:child.end_byte].decode('utf8')
        return 'private'

    def _extract_attributes(self, node: Node, src: bytes) -> list:
        attributes = []
        parent = node.parent
        if parent:
            for sibling in parent.children:
                if sibling.type == 'attribute_item' and sibling.end_point[0] < node.start_point[0]:
                    attr_text = src[sibling.start_byte:sibling.end_byte].decode('utf8')
                    attributes.append(attr_text)
        return attributes

    def _process_node(self, node: Node, src: bytes, file_path: str, current_module_path: str = None) -> dict:
        if current_module_path is None:
            current_module_path = self.module_stack[-1] if self.module_stack else self.current_module_path
        primary_kinds = {
            'mod_item', 'use_declaration', 'struct_item', 'enum_item', 'union_item',
            'type_alias_item', 'trait_item', 'impl_item', 'const_item', 'static_item',
            'function_item', 'closure_expression', 'let_declaration', 'type_item'
        }
        if node.type not in primary_kinds:
            return None
        name = self._extract_name(node, src)
        if node.type == 'mod_item':
            full_module_path = f"{current_module_path}::{name}" if current_module_path != "crate" else f"crate::{name}"
        else:
            full_module_path = current_module_path
        span = {
            'start_line': node.start_point[0] + 1,
            'end_line': node.end_point[0] + 1,
            'start_byte': node.start_byte,
            'end_byte': node.end_byte,
        }
        comp = {
            'type': node.type,
            'name': name,
            'file_path': file_path,
            'module_path': full_module_path,
            'span': span,
            'code': src[node.start_byte:node.end_byte].decode('utf8', errors='ignore'),
            'visibility': self._extract_visibility(node, src),
            'attributes': self._extract_attributes(node, src),
            'children': [],
            'parameters': [],
            'return_type': None,
            'type_parameters': [],
            'where_clause': None,
            'function_calls': [],
            'method_calls': [],
            'macro_calls': [],
            'literals': [],
            'variables': [],
            'types_used': [],
            'imports': [],
            'fields': [],
            'variants': [],  
            'trait_bounds': [],
            'lifetimes': []
        }
        self._extract_node_specific_info(node, src, comp)
        if node.type == 'mod_item':
            self.module_stack.append(full_module_path)
            self._traverse_and_extract(node, src, comp, file_path)
            self.module_stack.pop()
        else:
            self._traverse_and_extract(node, src, comp, file_path)
        return comp

    def _extract_name(self, node: Node, src: bytes) -> str:
        if node.type == 'impl_item':
            return self._extract_impl_name(node, src)
        elif node.type == 'use_declaration':
            return self._extract_use_name(node, src)
        else:
            name_node = (node.child_by_field_name('name') or 
                        node.child_by_field_name('path') or
                        node.child_by_field_name('pattern'))
            if name_node:
                return src[name_node.start_byte:name_node.end_byte].decode('utf8')
            return node.type

    def _extract_impl_name(self, node: Node, src: bytes) -> str:
        trait_node = node.child_by_field_name('trait')
        type_node = node.child_by_field_name('type')
        if trait_node and type_node:
            trait_name = src[trait_node.start_byte:trait_node.end_byte].decode('utf8')
            type_name = src[type_node.start_byte:type_node.end_byte].decode('utf8')
            return f"{trait_name} for {type_name}"
        elif type_node:
            type_name = src[type_node.start_byte:type_node.end_byte].decode('utf8')
            return f"impl {type_name}"
        return 'impl_item'

    def _extract_use_name(self, node: Node, src: bytes) -> str:
        arg_node = node.child_by_field_name('argument')
        if arg_node:
            return self._extract_use_module_path(arg_node, src)
        return 'use_declaration'

    def _extract_use_module_path(self, node: Node, src: bytes) -> str:
        if node.type == 'scoped_use_list':
            path_node = node.child_by_field_name('path')
            if path_node:
                return src[path_node.start_byte:path_node.end_byte].decode('utf8')
        elif node.type == 'scoped_identifier':
            return src[node.start_byte:node.end_byte].decode('utf8')
        elif node.type == 'identifier':
            return src[node.start_byte:node.end_byte].decode('utf8')
        elif node.type == 'crate':
            return 'crate'
        else:
            return src[node.start_byte:node.end_byte].decode('utf8')

    def _extract_node_specific_info(self, node: Node, src: bytes, comp: dict):
        if node.type == 'function_item':
            self._extract_function_info(node, src, comp)
        elif node.type == 'struct_item':
            self._extract_struct_info(node, src, comp)
        elif node.type == 'enum_item':
            self._extract_enum_info(node, src, comp)
        elif node.type == 'trait_item':
            self._extract_trait_info(node, src, comp)
        elif node.type == 'impl_item':
            self._extract_impl_info(node, src, comp)
        elif node.type == 'use_declaration':
            self._extract_use_info(node, src, comp)
        elif node.type == 'mod_item':
            self._extract_mod_info(node, src, comp)

    def _extract_function_info(self, node: Node, src: bytes, comp: dict):
        params_node = node.child_by_field_name('parameters')
        if params_node:
            for param in params_node.named_children:
                if param.type == 'parameter':
                    pattern = param.child_by_field_name('pattern')
                    type_node = param.child_by_field_name('type')
                    param_info = {
                        'name': src[pattern.start_byte:pattern.end_byte].decode('utf8') if pattern else '',
                        'type': self._extract_type_info(type_node, src) if type_node else None
                    }
                    comp['parameters'].append(param_info)
                elif param.type == 'self_parameter':
                    comp['parameters'].append({'name': 'self', 'type': 'Self'})
        ret_node = node.child_by_field_name('return_type')
        if ret_node:
            comp['return_type'] = self._extract_type_info(ret_node, src)
        type_params = node.child_by_field_name('type_parameters')
        if type_params:
            comp['type_parameters'] = src[type_params.start_byte:type_params.end_byte].decode('utf8')
        where_node = None
        for child in node.children:
            if child.type == 'where_clause':
                where_node = child
                break
        if where_node:
            comp['where_clause'] = src[where_node.start_byte:where_node.end_byte].decode('utf8')

    def _extract_struct_info(self, node: Node, src: bytes, comp: dict):
        body = node.child_by_field_name('body')
        if body:
            if body.type == 'field_declaration_list':
                for field in body.named_children:
                    if field.type == 'field_declaration':
                        name_node = field.child_by_field_name('name')
                        type_node = field.child_by_field_name('type')
                        field_info = {
                            'name': src[name_node.start_byte:name_node.end_byte].decode('utf8') if name_node else '',
                            'type': self._extract_type_info(type_node, src) if type_node else '',
                            'visibility': self._extract_visibility(field, src)
                        }
                        comp['fields'].append(field_info)
            elif body.type == 'ordered_field_declaration_list':
                for i, field in enumerate(body.named_children):
                    field_info = {
                        'name': f"field_{i}",
                        'type': self._extract_type_info(field, src),
                        'visibility': self._extract_visibility(field, src)
                    }
                    comp['fields'].append(field_info)

    def _extract_enum_info(self, node: Node, src: bytes, comp: dict):
        body = node.child_by_field_name('body')
        if body and body.type == 'enum_variant_list':
            for variant in body.named_children:
                if variant.type == 'enum_variant':
                    name_node = variant.child_by_field_name('name')
                    variant_info = {
                        'name': src[name_node.start_byte:name_node.end_byte].decode('utf8') if name_node else '',
                        'fields': []
                    }
                    value_node = variant.child_by_field_name('value')
                    if value_node:
                        if value_node.type == 'field_declaration_list':
                            for field in value_node.named_children:
                                field_name = field.child_by_field_name('name')
                                field_type = field.child_by_field_name('type')
                                variant_info['fields'].append({
                                    'name': src[field_name.start_byte:field_name.end_byte].decode('utf8') if field_name else '',
                                    'type': self._extract_type_info(field_type, src) if field_type else ''
                                })
                        elif value_node.type == 'ordered_field_declaration_list':
                            for i, field in enumerate(value_node.named_children):
                                variant_info['fields'].append({
                                    'name': f"field_{i}",
                                    'type': self._extract_type_info(field, src)
                                })
                    comp['variants'].append(variant_info)

    def _extract_trait_info(self, node: Node, src: bytes, comp: dict):
        pass

    def _extract_impl_info(self, node: Node, src: bytes, comp: dict):
        type_params = node.child_by_field_name('type_parameters')
        if type_params:
            comp['type_parameters'] = src[type_params.start_byte:type_params.end_byte].decode('utf8')

    def _extract_use_info(self, node: Node, src: bytes, comp: dict):
        def extract_imports_from_node(n: Node, base_path: str = ""):
            if n.type == 'identifier':
                import_path = f"{base_path}::{src[n.start_byte:n.end_byte].decode('utf8')}" if base_path else src[n.start_byte:n.end_byte].decode('utf8')
                comp['imports'].append(import_path)
            elif n.type == 'scoped_identifier':
                path_node = n.child_by_field_name('path')
                name_node = n.child_by_field_name('name')
                if path_node and name_node:
                    path_str = src[path_node.start_byte:path_node.end_byte].decode('utf8')
                    name_str = src[name_node.start_byte:name_node.end_byte].decode('utf8')
                    full_path = f"{base_path}::{path_str}::{name_str}" if base_path else f"{path_str}::{name_str}"
                    comp['imports'].append(full_path)
            elif n.type == 'scoped_use_list':
                path_node = n.child_by_field_name('path')
                list_node = n.child_by_field_name('list')
                if path_node and list_node:
                    path_str = src[path_node.start_byte:path_node.end_byte].decode('utf8')
                    current_base = f"{base_path}::{path_str}" if base_path else path_str
                    for child in list_node.named_children:
                        extract_imports_from_node(child, current_base)
            elif n.type == 'use_list':
                for child in n.named_children:
                    extract_imports_from_node(child, base_path)
            elif n.type == 'crate':
                return "crate"
        arg_node = node.child_by_field_name('argument')
        if arg_node:
            extract_imports_from_node(arg_node)

    def _extract_mod_info(self, node: Node, src: bytes, comp: dict):
        pass

    def _traverse_and_extract(self, node: Node, src: bytes, comp: dict, file_path: str):
        def walk(n: Node):
            t = n.type
            primary_kinds = {
                'mod_item', 'use_declaration', 'struct_item', 'enum_item', 'union_item',
                'type_alias_item', 'trait_item', 'impl_item', 'const_item', 'static_item',
                'function_item', 'closure_expression', 'type_item'
            }
            if t in primary_kinds and n is not node:
                child = self._process_node(n, src, file_path, self.module_stack[-1] if self.module_stack else self.current_module_path)
                if child:
                    comp['children'].append(child)
                return
            if t == 'call_expression':
                fn = n.child_by_field_name('function')
                if fn:
                    if fn.type == 'field_expression':
                        value_node = fn.child_by_field_name('value')
                        field_node = fn.child_by_field_name('field')
                        if value_node and field_node:
                            receiver_text = src[value_node.start_byte:value_node.end_byte].decode('utf8')
                            method_text = src[field_node.start_byte:field_node.end_byte].decode('utf8')
                            resolved_receiver = self._resolve_symbol_path(receiver_text)
                            method_info = {
                                'receiver': receiver_text,
                                'resolved_receiver': resolved_receiver,
                                'method': method_text,
                                'full_path': f"{resolved_receiver}::{method_text}",
                                'span': {
                                    'start_line': n.start_point[0] + 1,
                                    'end_line': n.end_point[0] + 1
                                }
                            }
                            comp['method_calls'].append(method_info)
                    else:
                        fn_text = src[fn.start_byte:fn.end_byte].decode('utf8')
                        resolved_fn = self._resolve_symbol_path(fn_text)
                        call_info = {
                            'name': fn_text,
                            'resolved_name': resolved_fn,
                            'span': {
                                'start_line': n.start_point[0] + 1,
                                'end_line': n.end_point[0] + 1
                            }
                        }
                        comp['function_calls'].append(call_info)
            elif t == 'macro_invocation':
                macro_node = n.child_by_field_name('macro')
                if macro_node:
                    macro_text = src[macro_node.start_byte:macro_node.end_byte].decode('utf8')
                    resolved_macro = self._resolve_symbol_path(macro_text)
                    macro_info = {
                        'name': macro_text,
                        'resolved_name': resolved_macro,
                        'span': {
                            'start_line': n.start_point[0] + 1,
                            'end_line': n.end_point[0] + 1
                        }
                    }
                    comp['macro_calls'].append(macro_info)
            elif t in {'string_literal', 'integer_literal', 'float_literal', 
                    'boolean_literal', 'char_literal', 'raw_string_literal'}:
                literal_info = {
                    'type': t,
                    'value': src[n.start_byte:n.end_byte].decode('utf8'),
                    'span': {
                        'start_line': n.start_point[0] + 1,
                        'end_line': n.end_point[0] + 1
                    }
                }
                comp['literals'].append(literal_info)
            elif t == 'let_declaration':
                pat = n.child_by_field_name('pattern')
                init = n.child_by_field_name('value')
                type_node = n.child_by_field_name('type')
                if pat:
                    var_info = {
                        'name': src[pat.start_byte:pat.end_byte].decode('utf8'),
                        'type': self._extract_type_info(type_node, src) if type_node else None,
                        'value': src[init.start_byte:init.end_byte].decode('utf8') if init else None,
                        'span': {
                            'start_line': n.start_point[0] + 1,
                            'end_line': n.end_point[0] + 1
                        }
                    }
                    comp['variables'].append(var_info)
            elif t in {'type_identifier', 'primitive_type', 'generic_type', 'scoped_type_identifier'}:
                type_text = src[n.start_byte:n.end_byte].decode('utf8')
                resolved_type = self._resolve_symbol_path(type_text)
                type_info = {
                    'type': type_text,
                    'resolved_type': resolved_type
                }
                if not any(existing['type'] == type_text for existing in comp['types_used']):
                    comp['types_used'].append(type_info)
            elif t == 'lifetime':
                lifetime_text = src[n.start_byte:n.end_byte].decode('utf8')
                if lifetime_text not in comp['lifetimes']:
                    comp['lifetimes'].append(lifetime_text)
            for child in n.named_children:
                walk(child)
        walk(node)
