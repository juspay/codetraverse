import tree_sitter_haskell
from tree_sitter import Language, Parser, Node
import json
import re
from collections import defaultdict
from base.component_extractor import ComponentExtractor

class HaskellComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.HS_LANGUAGE = Language(tree_sitter_haskell.language())
        self.parser = Parser(self.HS_LANGUAGE)
        self.import_map = {}
        self.all_components = []
        self.current_module = ""
        self.current_file_path = ""

    def process_file(self, file_path):
        with open(file_path, "rb") as f:
            src = f.read()
        self.current_file_path = file_path

        tree = self.parser.parse(src)
        self.import_map = self.parse_imports(tree.root_node, src)
        
        for child in tree.root_node.children:
            if child.type == "header":
                module_path = []
                module_node = child.child_by_field_name("module")
                if module_node:
                    for module_id in module_node.children:
                        if module_id.type == "module_id":
                            module_path.append(src[module_id.start_byte:module_id.end_byte].decode())
                self.current_module = ".".join(module_path)
                break
        
        raw_groups = [self.extract_top_level_components(i, src, import_map=self.import_map) for i in tree.root_node.children]
        self.all_components = [c for group in raw_groups for c in group]

        for comp in self.all_components:
            comp["file_path"] = self.current_file_path

        for comp in self.all_components:
            if comp["kind"] == "function":
                comp["type_dependencies"] = self.find_type_dependencies(comp["name"], self.all_components)

    def write_to_file(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)
    
    def extract_all_components(self):
        return self.all_components

    def parse_imports(self, root_node, src_bytes):
        import_map = defaultdict(list)
        def traverse(node):
            if node.type == "import":
                module_node = node.child_by_field_name("module")
                if module_node:
                    module = src_bytes[module_node.start_byte:module_node.end_byte].decode()
                    alias_node = node.child_by_field_name("alias")
                    alias = module.split(".")[-1]
                    if alias_node:
                        alias = src_bytes[alias_node.start_byte:alias_node.end_byte].decode()
                    import_map[alias].append(module)
            for child in node.children:
                traverse(child)
        traverse(root_node)
        return dict(import_map)

    def extract_top_level_components(self, root_node, src_bytes, import_map):
        TOP_LEVEL_KINDS = {
            "header", "pragma", "import", "imports",
            "decl", "type_synonym", "kind_signature", "type_family", "type_instance",
            "role_annotation", "data_type", "newtype", "data_family", "data_instance",
            "class", "instance", "default_types", "deriving_instance", "pattern_synonym",
            "foreign_import", "foreign_export", "fixity", "top_splice", "signature",
            "function", "bind",
        }

        sigs = {}
        for child in root_node.children:
            if child.type == "signature":
                start, end = child.start_point[0], child.end_point[0]
                sig_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = src_bytes[name_node.start_byte:name_node.end_byte].decode()
                    sigs[name] = sig_code
    
        components = []

        if root_node.type == "header":
            start, end = root_node.start_point[0], root_node.end_point[0]
            header_code = b"\n".join(src_bytes.split(b"\n")[start:end+1]).decode("utf8")

            module_path = []
            mod_n = root_node.child_by_field_name("module")
            if mod_n:
                for mid in mod_n.named_children:
                    if mid.type == "module_id":
                        module_path.append(src_bytes[mid.start_byte:mid.end_byte].decode())

            exports = []
            exp_n = root_node.child_by_field_name("exports")
            if exp_n:
                for item in exp_n.named_children:
                    if item.type == "module_export":
                        alias = item.child_by_field_name("module")
                        if alias:
                            exports.append(src_bytes[alias.start_byte:alias.end_byte].decode())
                    elif item.type in ("export","import_name","name"):
                        txt = src_bytes[item.start_byte:item.end_byte].decode().strip()
                        exports.append(txt)

            if not exports:
                parent = root_node.parent
                for sib in parent.children:
                    for child in sib.children:
                        if child is root_node:
                            continue
                        if child.type in ("function","data_type","instance","class","newtype","type_synonym"):
                            name_n = child.child_by_field_name("name") or child.child_by_field_name("variable")
                            if name_n:
                                exports.append(src_bytes[name_n.start_byte:name_n.end_byte].decode())

            components.append({
                "kind":        "module_header",
                "name":        ".".join(module_path),
                "start_line":  start+1,
                "end_line":    end+1,
                "code":        header_code,
                "module_path": module_path,
                "exports":     exports
            })
            return components
        
        for child in root_node.children:
            if child.type == "header":
                print("Skipping header node in top-level extraction")
                start, end = child.start_point[0], child.end_point[0]
                header_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
                module_path = []
                module_node = child.child_by_field_name("module")
                if module_node:
                    for module_id in module_node.children:
                        if module_id.type == "module_id":
                            module_path.append(src_bytes[module_id.start_byte:module_id.end_byte].decode())
                components.append({
                    "kind": "module_header",
                    "name": ".".join(module_path),
                    "start_line": start + 1,
                    "end_line": end + 1,
                    "code": header_code,
                    "module_path": module_path
                })
            elif child.type == "pragma":
                start, end = child.start_point[0], child.end_point[0]
                pragma_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
                pragma_content = pragma_code.strip().strip("{-#").strip("#-}").strip()
                components.append({
                    "kind": "pragma",
                    "name": pragma_content,
                    "start_line": start + 1,
                    "end_line": end + 1,
                    "code": pragma_code
                })
            elif child.type == "imports":
                for import_node in child.children:
                    if import_node.type == "import":
                        comp = self.extract_import_component(import_node, src_bytes)
                        if comp:
                            components.append(comp)
            elif child.type == "import":
                comp = self.extract_import_component(child, src_bytes)
                if comp:
                    components.append(comp)
            elif child.type == "function":
                name_node = child.child_by_field_name("name")
                fn_name = src_bytes[name_node.start_byte:name_node.end_byte].decode() if name_node else "unknown"
                
                # Extract body without where clause
                body_node = child.child_by_field_name("match")
                body_code = src_bytes[body_node.start_byte:body_node.end_byte].decode() if body_node else ""
                
                # Extract entire function code
                start, end = child.start_point[0], child.end_point[0]
                entire_func_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
                
                comp = {
                    "kind": "function",
                    "name": fn_name,
                    "module": self.current_module,
                    "start_line": start + 1,
                    "end_line": end + 1,
                    "code": entire_func_code,
                }
                
                if fn_name in sigs:
                    comp["type_signature"] = sigs[fn_name]
                
                # Extract function calls from body
                comp["function_calls"] = self.extract_function_calls(body_code, import_map, self.current_module)
                
                # Extract where definitions using Tree-sitter
                where_defs = self.extract_where_definitions(child, src_bytes)
                if where_defs:
                    comp["where_definitions"] = where_defs
                    for where_def in where_defs:
                        if where_def["kind"] == "function":
                            where_def["function_calls"] = self.extract_function_calls(
                                where_def["code"], import_map, self.current_module
                            )
                
                components.append(comp)
                comp["reexported_from"] = reexported_modules.get(self.current_module, [])
            elif child.type == "instance":
                instance_comp = self.extract_instance_component(child, src_bytes, import_map)
                if instance_comp:
                    instance_comp["module"] = self.current_module
                    instance_comp["function_calls"] = self.extract_function_calls(
                        instance_comp["code"], import_map, self.current_module
                    )
                    components.append(instance_comp)
            elif child.type == "data_type":
                data_comp = self.extract_data_type_component(child, src_bytes, import_map)
                if data_comp:
                    data_comp["module"] = self.current_module
                    data_comp["function_calls"] = self.extract_function_calls(
                        data_comp["code"], import_map, self.current_module
                    )
                    components.append(data_comp)
            reexported_modules = defaultdict(list)

        reexported_modules = defaultdict(list)   
        for comp in components:
            if comp["kind"] == "import" and comp["alias"]:
                reexported_modules[comp["module"]].append(comp["alias"])

        return components
    
    def extract_where_definitions(self, function_node, src_bytes):
        """Extract where definitions using Tree-sitter nodes"""
        where_defs = []
        for node in function_node.children:
            if node.type == "local_binds":
                for bind_node in node.children:
                    if bind_node.type != "bind":
                        continue
                    
                    name_node = bind_node.child_by_field_name("name")
                    if not name_node:
                        continue
                    name = src_bytes[name_node.start_byte:name_node.end_byte].decode()
                    
                    start, end = bind_node.start_point[0], bind_node.end_point[0]
                    code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
                    
                    where_defs.append({
                        "kind": "function",
                        "name": name,
                        "code": code
                    })
        return where_defs

    def extract_import_component(self, import_node, src_bytes):
        start, end = import_node.start_point[0], import_node.end_point[0]
        import_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
        module_node = import_node.child_by_field_name("module")
        module_name = src_bytes[module_node.start_byte:module_node.end_byte].decode() if module_node else None
        alias_node = import_node.child_by_field_name("alias")
        alias = src_bytes[alias_node.start_byte:alias_node.end_byte].decode() if alias_node else None
        import_list = []
        names_node = import_node.child_by_field_name("names")
        if names_node:
            for name_child in names_node.children:
                if name_child.type == "import_name":
                    for id_child in name_child.children:
                        if id_child.type in ["name", "variable"]:
                            import_list.append(
                                src_bytes[id_child.start_byte:id_child.end_byte].decode()
                            )
        is_qualified = "qualified" in import_code
        is_hiding = "hiding" in import_code
        return {
            "kind": "import",
            "module": module_name,
            "alias": alias,
            "import_list": import_list,
            "is_qualified": is_qualified,
            "is_hiding": is_hiding,
            "start_line": start + 1,
            "end_line": end + 1,
            "code": import_code
        }

    def extract_data_type_component(self, data_node, src_bytes, import_map):
        start, end = data_node.start_point[0], data_node.end_point[0]
        data_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
        data_name = self.extract_data_type_name(data_node, src_bytes)
        constructors = []
        for child in data_node.children:
            if child.type == "data_constructors":
                constructors = self.extract_data_constructors(child, src_bytes)
        deriving_info = []
        for child in data_node.children:
            if child.type == "deriving":
                deriving_info = self.extract_deriving_clause(child, src_bytes)
        comp = {
            "kind": "data_type",
            "name": data_name,
            "start_line": start + 1,
            "end_line": end + 1,
            "code": data_code,
            "constructors": constructors,
            "deriving": deriving_info
        }
        return comp
    
    def extract_data_type_name(self, data_node, src_bytes):
        name_node = data_node.child_by_field_name("name")
        if name_node:
            return src_bytes[name_node.start_byte:name_node.end_byte].decode()
        return "UnknownDataType"

    def extract_data_constructors(self, constructors_node, src_bytes):
        constructors = []
        for child in constructors_node.children:
            if child.type == "data_constructor":
                constructor = self.extract_single_constructor(child, src_bytes)
                if constructor:
                    constructors.append(constructor)
        return constructors

    def extract_single_constructor(self, constructor_node, src_bytes):
        constructor_info = {
            "type": "constructor",
            "name": "Unknown",
            "fields": []
        }
        for child in constructor_node.children:
            if child.type == "record":
                constructor_info["type"] = "record"
                constructor_info["name"] = self.extract_constructor_name(child, src_bytes)
                constructor_info["fields"] = self.extract_record_fields(child, src_bytes)
            elif child.type == "constructor":
                constructor_info["name"] = src_bytes[child.start_byte:child.end_byte].decode()
        return constructor_info

    def extract_constructor_name(self, record_node, src_bytes):
        name_node = record_node.child_by_field_name("constructor")
        if name_node:
            return src_bytes[name_node.start_byte:name_node.end_byte].decode()
        return "UnknownConstructor"

    def extract_record_fields(self, record_node, src_bytes):
        fields = []
        fields_node = record_node.child_by_field_name("fields")
        if fields_node:
            for field_child in fields_node.children:
                if field_child.type == "field":
                    field_info = self.extract_field_info(field_child, src_bytes)
                    if field_info:
                        fields.append(field_info)
        return fields

    def extract_field_info(self, field_node, src_bytes):
        name_node = field_node.child_by_field_name("name")
        field_name = src_bytes[name_node.start_byte:name_node.end_byte].decode() if name_node else None
        type_node = field_node.child_by_field_name("type")
        type_txt = src_bytes[type_node.start_byte:type_node.end_byte].decode() if type_node else None
        core = type_txt
        if core and " " in core:
            core = core.split()[-1]
        if core and "." in core:
            module_part, base = core.rsplit(".", 1)
            resolved = self.import_map.get(module_part, [module_part])
            modules = [f"{m}.{base}" for m in resolved]
            type_info = {
                "name":    f"{module_part}.{base}",
                "type":    "qualified",
                "modules": modules,
                "base":    base,
                "context": "type_constructor"
            }
        else:
            type_info = {
                "name":    core,
                "type":    "simple",
                "modules": [],
                "base":    core,
                "context": "type_constructor"
            }
        return {
            "name":      field_name,
            "type":      type_txt,
            "type_info": type_info
        }

    def _extract_qualified_type(self, qualified_node, src_bytes):
        module_bits = []
        module_node = qualified_node.child_by_field_name("module")
        if module_node:
            for m in module_node.children:
                if m.type == "module_id":
                    module_bits.append(src_bytes[m.start_byte:m.end_byte].decode())
        base_node = qualified_node.child_by_field_name("id") or qualified_node.child_by_field_name("name")
        base = src_bytes[base_node.start_byte:base_node.end_byte].decode() if base_node else ""
        full = ".".join(module_bits + ([base] if base else []))
        first = module_bits[0] if module_bits else None
        if first and first in self.import_map:
            modules = [f"{imp}.{'.'.join(module_bits[1:])}" for imp in self.import_map[first]]
        else:
            modules = [".".join(module_bits)] if module_bits else []
        return {"full": full, "modules": modules, "base": base}

    def extract_type_info(self, type_node, src_bytes):
        if type_node.type == "name":
            return src_bytes[type_node.start_byte:type_node.end_byte].decode()
        elif type_node.type == "qualified":
            return self.extract_qualified_type(type_node, src_bytes)
        elif type_node.type == "apply":
            return self.extract_applied_type(type_node, src_bytes)
        else:
            return src_bytes[type_node.start_byte:type_node.end_byte].decode()

    def extract_qualified_type(self, qualified_node, src_bytes):
        module_part = ""
        id_part = ""
        module_node = qualified_node.child_by_field_name("module")
        if module_node:
            for module_child in module_node.children:
                if module_child.type == "module_id":
                    module_part = src_bytes[module_child.start_byte:module_child.end_byte].decode()
        base_node = qualified_node.child_by_field_name("id") or qualified_node.child_by_field_name("name")
        if base_node:
            id_part = src_bytes[base_node.start_byte:base_node.end_byte].decode()
        return f"{module_part}.{id_part}" if module_part and id_part else id_part

    def extract_applied_type(self, apply_node, src_bytes):
        constructor = ""
        argument = ""
        for child in apply_node.children:
            if child.type == "name":
                constructor = src_bytes[child.start_byte:child.end_byte].decode()
            elif child.type in ["qualified", "name"]:
                argument = self.extract_type_info(child, src_bytes)
        return f"{constructor} {argument}" if constructor and argument else constructor

    def extract_deriving_clause(self, deriving_node, src_bytes):
        deriving_info = {
            "strategy": None,
            "classes": []
        }
        for child in deriving_node.children:
            if child.type == "deriving_strategy":
                deriving_info["strategy"] = src_bytes[child.start_byte:child.end_byte].decode()
            elif child.type == "tuple":
                for tuple_child in child.children:
                    if tuple_child.type == "name":
                        class_name = src_bytes[tuple_child.start_byte:tuple_child.end_byte].decode()
                        deriving_info["classes"].append(class_name)
        return deriving_info

    def extract_instance_component(self, instance_node, src_bytes, import_map):
        start, end = instance_node.start_point[0], instance_node.end_point[0]
        instance_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
        instance_name = self.extract_instance_name(instance_node, src_bytes)
        type_patterns = self.extract_type_patterns(instance_node, src_bytes)
        instance_methods = []
        type_instances = []
        for child in instance_node.children:
            if child.type == "instance_declarations":
                for decl in child.children:
                    if decl.type == "declaration":
                        for inner_decl in decl.children:
                            if inner_decl.type == "bind":
                                method = self.extract_instance_method(inner_decl, src_bytes, import_map)
                                if method:
                                    instance_methods.append(method)
                            elif inner_decl.type == "type_instance":
                                type_inst = self.extract_type_instance(inner_decl, src_bytes)
                                if type_inst:
                                    type_instances.append(type_inst)
        comp = {
            "kind": "instance",
            "name": instance_name,
            "start_line": start + 1,
            "end_line": end + 1,
            "code": instance_code,
            "type_patterns": type_patterns,
            "instance_methods": instance_methods,
            "type_instances": type_instances
        }
        return comp

    def extract_instance_name(self, instance_node, src_bytes):
        name_node = instance_node.child_by_field_name("name")
        if name_node:
            return src_bytes[name_node.start_byte:name_node.end_byte].decode()
        return "UnknownInstance"

    def extract_type_patterns(self, instance_node, src_bytes):
        patterns = []
        type_patterns_node = instance_node.child_by_field_name("type_patterns")
        if type_patterns_node:
            for pattern in type_patterns_node.children:
                if pattern.type == "qualified":
                    qualified_info = self.extract_qualified_info(pattern, src_bytes)
                    patterns.append(qualified_info)
                else:
                    pattern_text = src_bytes[pattern.start_byte:pattern.end_byte].decode()
                    patterns.append({
                        'name': pattern_text,
                        'type': 'simple',
                        'context': 'type_pattern'
                    })
        return patterns

    def extract_qualified_info(self, qualified_node, src_bytes):
        module_part = ""
        id_part = ""
        module_node = qualified_node.child_by_field_name("module")
        if module_node:
            for module_child in module_node.children:
                if module_child.type == "module_id":
                    module_part = src_bytes[module_child.start_byte:module_child.end_byte].decode()
        base_node = qualified_node.child_by_field_name("id") or qualified_node.child_by_field_name("name")
        if base_node:
            id_part = src_bytes[base_node.start_byte:base_node.end_byte].decode()
        if module_part and id_part:
            full_name = f"{module_part}.{id_part}"
            resolved_modules = [module_part]
            if module_part in self.import_map:
                resolved_modules = self.import_map[module_part]
            return {
                'name': full_name,
                'type': 'qualified',
                'modules': resolved_modules,
                'base': id_part,
                'context': 'type_pattern'
            }
        elif id_part:
            return {
                'name': id_part,
                'type': 'simple',
                'context': 'type_pattern'
            }
        else:
            fallback_name = src_bytes[qualified_node.start_byte:qualified_node.end_byte].decode()
            return {
                'name': fallback_name,
                'type': 'fallback',
                'context': 'type_pattern'
            }

    def extract_instance_method(self, bind_node, src_bytes, import_map):
        method_name = ""
        name_node = bind_node.child_by_field_name("name")
        if name_node:
            method_name = src_bytes[name_node.start_byte:name_node.end_byte].decode()
        start, end = bind_node.start_point[0], bind_node.end_point[0]
        method_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
        method = {
            "kind": "instance_method",
            "name": method_name,
            "code": method_code.strip()
        }
        return method

    def extract_type_instance(self, type_instance_node, src_bytes):
        type_name = ""
        name_node = type_instance_node.child_by_field_name("name")
        if name_node:
            type_name = src_bytes[name_node.start_byte:name_node.end_byte].decode()
        type_patterns = []
        type_patterns_node = type_instance_node.child_by_field_name("type_patterns")
        if type_patterns_node:
            for pattern in type_patterns_node.children:
                if pattern.type == "qualified":
                    qualified_info = self.extract_qualified_info(pattern, src_bytes)
                    type_patterns.append(qualified_info)
                else:
                    pattern_text = src_bytes[pattern.start_byte:pattern.end_byte].decode()
                    type_patterns.append({
                        'name': pattern_text,
                        'type': 'simple',
                        'context': 'type_pattern'
                    })
        type_definition = ""
        value_node = type_instance_node.child_by_field_name("value")
        if value_node:
            if value_node.type == "qualified":
                type_definition = self.extract_qualified_info(value_node, src_bytes)
            else:
                type_definition = {
                    'name': src_bytes[value_node.start_byte:value_node.end_byte].decode(),
                    'type': 'simple',
                    'context': 'type_definition'
                }
        return {
            "kind": "type_instance",
            "name": type_name,
            "type_patterns": type_patterns,
            "type_definition": type_definition
        }

    def extract_function_calls(self, func_code: str, import_map: dict, current_module: str):
        lines = func_code.split('\n')
        identifiers = []
        string_pattern = re.compile(r'"(?:[^"\\]|\\.)*"')
        operator_pattern = re.compile(r'\((\S+)\)')
        qualified_name_pattern = re.compile(r'\b((?:[A-Z][a-zA-Z0-9_]*\.)+)([a-z][a-zA-Z0-9_\']*)\b')
        list_pattern = re.compile(r'\[(.*?)\]')
        tuple_pattern = re.compile(r'\(([^)]*,.*?)\)')
        record_pattern = re.compile(r'\{(.*?)\}')
        lambda_pattern = re.compile(r'\\[^>]+->')
        numeric_literal_pattern = re.compile(r'\b\d+(?:\.\d+)?\b')
        collection_patterns = {
            'Map': ['lookup', 'insert', 'delete', 'fromList', 'toList'],
            'Set': ['fromList', 'toList', 'union', 'difference']
        }
        
        skip_keywords = {'if', 'then', 'else', 'let', 'in', 'do', 'case', 'of', 'where', 'data', 'type', 
                        'newtype', 'class', 'instance', 'deriving', 'import', 'module', 'as', 'hiding', 
                        'qualified', 'infix', 'infixl', 'infixr', 'pure', 'return', 'mempty', 'mappend'}
        
        for line in lines:
            line = re.sub(r'--.*', '', line)
            line = string_pattern.sub('', line)
            
            if '::' in line or line.strip().startswith('instance') or line.strip().startswith('where'):
                continue
                
            for match in qualified_name_pattern.finditer(line):
                prefix = match.group(1).rstrip('.')
                base_name = match.group(2)
                
                if not prefix or base_name in skip_keywords:
                    continue
                    
                resolved_modules = [prefix]
                components = prefix.split('.')
                if components:
                    first_component = components[0]
                    resolved = import_map.get(first_component, [first_component])
                    if len(components) > 1:
                        resolved = [f"{r}.{'.'.join(components[1:])}" for r in resolved]
                    resolved_modules = resolved
                    
                identifiers.append({
                    'name': f"{prefix}.{base_name}",
                    'type': 'qualified',
                    'modules': resolved_modules,
                    'base': base_name,
                    'context': 'function_call'
                })
            
            for call in re.findall(r'\b([a-z][a-zA-Z0-9_\']*)\s*(?=\()', line):
                if call in skip_keywords:
                    continue
                identifiers.append({
                    'name': call,
                    'type': 'function',
                    'modules': [current_module],
                    'base': call,
                    'context': 'function_call'
                })
            
            operators = operator_pattern.findall(line)
            for op in operators:
                if op in skip_keywords:
                    continue
                identifiers.append({
                    'name': op,
                    'type': 'operator',
                    'context': 'operation'
                })
            
            for list_match in list_pattern.finditer(line):
                elements = [e.strip() for e in list_match.group(1).split(',')]
                identifiers.append({
                    'name': list_match.group(0),
                    'type': 'literal',
                    'subtype': 'list',
                    'elements': elements
                })
            
            for tuple_match in tuple_pattern.finditer(line):
                elements = [e.strip() for e in tuple_match.group(1).split(',')]
                identifiers.append({
                    'name': tuple_match.group(0),
                    'type': 'literal',
                    'subtype': 'tuple',
                    'elements': elements,
                    'length': len(elements)
                })
            
            for record_match in record_pattern.finditer(line):
                fields = [f.strip() for f in record_match.group(1).split(',')]
                identifiers.append({
                    'name': record_match.group(0),
                    'type': 'record',
                    'fields': fields
                })
            
            if lambda_pattern.search(line):
                identifiers.append({
                    'name': 'λ',
                    'type': 'lambda',
                    'context': 'anonymous_function'
                })
            
            for coll_type, funcs in collection_patterns.items():
                for func in funcs:
                    if re.search(rf'\b{func}\b', line):
                        identifiers.append({
                            'name': func,
                            'type': 'collection_function',
                            'collection': coll_type,
                            'context': 'data_structure'
                        })
            
            for ctor in re.findall(r'\b([A-Z][a-zA-Z0-9_\']*)\b', line):
                if ctor in skip_keywords:
                    continue
                identifiers.append({
                    'name': ctor,
                    'type': 'type_constructor',
                    'context': 'type_system'
                })
            
            if '=' in line and 'type' not in line:
                for var in re.findall(r'\b([a-z][a-zA-Z0-9_\']*)\b', line):
                    if var in skip_keywords:
                        continue
                    identifiers.append({
                        'name': var,
                        'type': 'variable',
                        'context': 'binding'
                    })
            
            for num in numeric_literal_pattern.findall(line):
                identifiers.append({
                    'name': num,
                    'type': 'literal',
                    'subtype': 'numeric',
                    'value': float(num) if '.' in num else int(num)
                })
            
        seen = set()
        unique_identifiers = []
        for ident in identifiers:
            key = (ident['name'], ident.get('type'), ident.get('context'))
            if key not in seen:
                seen.add(key)
                unique_identifiers.append(ident)
        return unique_identifiers

    def find_type_dependencies(self, func_name, components):
        for comp in components:
            if comp.get("kind") == "function" and comp.get("name") == func_name:
                sig = comp.get("type_signature")
                if not sig:
                    return []
                type_part = sig.split("::", 1)[1]
                deps = re.findall(r'\b[A-Z][A-Za-z0-9_.]*', type_part)
                return sorted(set(deps))
        return []