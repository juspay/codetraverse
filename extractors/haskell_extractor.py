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

    def process_file(self, file_path):
        with open(file_path, "rb") as f:
            src = f.read()

        tree = self.parser.parse(src)
        self.import_map = self.parse_imports(tree.root_node, src)
        raw_groups = [self.extract_top_level_components(i, src, import_map=self.import_map) for i in tree.root_node.children]
        self.all_components = [c for group in raw_groups for c in group]

        for comp in self.all_components:
            if comp["kind"] == "function":
                fn_name = comp["code"].split()[0].split("(")[0]
                comp["type_dependencies"] = self.find_type_dependencies(fn_name, self.all_components)

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
                name = sig_code.split("::", 1)[0].strip()
                sigs[name] = sig_code

        components = []
        for child in root_node.children:
            if child.type == "function":
                start, end = child.start_point[0], child.end_point[0]
                func_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")

                fn_name = func_code.split()[0].split("(")[0]
                comp = {
                    "kind": "function",
                    "name": fn_name,
                    "start_line": start + 1,
                    "end_line": end + 1,
                    "code": func_code,
                }
                if fn_name in sigs:
                    comp["type_signature"] = sigs[fn_name]
                comp["function_calls"] = self.extract_function_calls(func_code, import_map)

                where_defs = self.extract_where_definitions(func_code)
                if where_defs:
                    comp["where_definitions"] = where_defs
                    for where_def in where_defs:
                        if where_def["kind"] == "function":
                            where_def["function_calls"] = self.extract_function_calls(
                                where_def["code"], import_map
                            )
                components.append(comp)
            
            elif child.type == "instance":
                # Handle instance declarations
                instance_comp = self.extract_instance_component(child, src_bytes, import_map)
                if instance_comp:
                    components.append(instance_comp)
            
            elif child.type == "data_type":
                # Handle data type declarations
                data_comp = self.extract_data_type_component(child, src_bytes, import_map)
                if data_comp:
                    components.append(data_comp)
        
        return components

    def extract_data_type_component(self, data_node, src_bytes, import_map):
        """Extract data type declaration components"""
        start, end = data_node.start_point[0], data_node.end_point[0]
        data_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
        
        # Extract data type name
        data_name = self.extract_data_type_name(data_node, src_bytes)
        
        # Extract constructors
        constructors = []
        for child in data_node.children:
            if child.type == "data_constructors":
                constructors = self.extract_data_constructors(child, src_bytes)
        
        # Extract deriving clauses
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
            "deriving": deriving_info,
            "function_calls": self.extract_function_calls(data_code, import_map)
        }
        
        return comp
    
    def extract_data_type_name(self, data_node, src_bytes):
        """Extract the data type name"""
        for child in data_node.children:
            if child.type == "name":
                return src_bytes[child.start_byte:child.end_byte].decode()
        return "UnknownDataType"

    def extract_data_constructors(self, constructors_node, src_bytes):
        """Extract data constructors"""
        constructors = []
        
        for child in constructors_node.children:
            if child.type == "data_constructor":
                constructor = self.extract_single_constructor(child, src_bytes)
                if constructor:
                    constructors.append(constructor)
        
        return constructors

    def extract_single_constructor(self, constructor_node, src_bytes):
        """Extract a single data constructor"""
        constructor_info = {
            "type": "constructor",
            "name": "Unknown",
            "fields": []
        }
        
        for child in constructor_node.children:
            if child.type == "record":
                # Handle record constructor
                constructor_info["type"] = "record"
                constructor_info["name"] = self.extract_constructor_name(child, src_bytes)
                constructor_info["fields"] = self.extract_record_fields(child, src_bytes)
            elif child.type == "constructor":
                # Handle simple constructor
                constructor_info["name"] = src_bytes[child.start_byte:child.end_byte].decode()
        
        return constructor_info

    def extract_constructor_name(self, record_node, src_bytes):
        """Extract constructor name from record"""
        for child in record_node.children:
            if child.type == "constructor":
                return src_bytes[child.start_byte:child.end_byte].decode()
        return "UnknownConstructor"

    def extract_record_fields(self, record_node, src_bytes):
        """Extract fields from record constructor"""
        fields = []
        
        for child in record_node.children:
            if child.type == "fields":
                for field_child in child.children:
                    if field_child.type == "field":
                        field_info = self.extract_field_info(field_child, src_bytes)
                        if field_info:
                            fields.append(field_info)
        
        return fields

    def extract_field_info(self, field_node, src_bytes):
        """Extract individual field information"""
        field_info = {
            "name": "unknown",
            "type": "unknown"
        }
        
        for child in field_node.children:
            if child.type == "field_name":
                # Extract field name
                for name_child in child.children:
                    if name_child.type == "variable":
                        field_info["name"] = src_bytes[name_child.start_byte:name_child.end_byte].decode()
            elif child.type in ["name", "qualified", "apply"]:
                # Extract field type
                field_info["type"] = self.extract_type_info(child, src_bytes)
        
        return field_info

    def extract_type_info(self, type_node, src_bytes):
        """Extract type information from various type nodes"""
        if type_node.type == "name":
            return src_bytes[type_node.start_byte:type_node.end_byte].decode()
        elif type_node.type == "qualified":
            return self.extract_qualified_type(type_node, src_bytes)
        elif type_node.type == "apply":
            return self.extract_applied_type(type_node, src_bytes)
        else:
            return src_bytes[type_node.start_byte:type_node.end_byte].decode()

    def extract_qualified_type(self, qualified_node, src_bytes):
        """Extract qualified type like Common.Payer"""
        module_part = ""
        id_part = ""
        
        for child in qualified_node.children:
            if child.type == "module":
                for module_child in child.children:
                    if module_child.type == "module_id":
                        module_part = src_bytes[module_child.start_byte:module_child.end_byte].decode()
            elif child.type == "name":
                id_part = src_bytes[child.start_byte:child.end_byte].decode()
        
        return f"{module_part}.{id_part}" if module_part and id_part else id_part

    def extract_applied_type(self, apply_node, src_bytes):
        """Extract applied type like Maybe Text"""
        constructor = ""
        argument = ""
        
        for child in apply_node.children:
            if child.type == "name":
                constructor = src_bytes[child.start_byte:child.end_byte].decode()
            elif child.type in ["qualified", "name"]:
                argument = self.extract_type_info(child, src_bytes)
        
        return f"{constructor} {argument}" if constructor and argument else constructor

    def extract_deriving_clause(self, deriving_node, src_bytes):
        """Extract deriving clause information"""
        deriving_info = {
            "strategy": None,
            "classes": []
        }
        
        for child in deriving_node.children:
            if child.type == "deriving_strategy":
                deriving_info["strategy"] = src_bytes[child.start_byte:child.end_byte].decode()
            elif child.type == "tuple":
                # Extract classes from tuple
                for tuple_child in child.children:
                    if tuple_child.type == "name":
                        class_name = src_bytes[tuple_child.start_byte:tuple_child.end_byte].decode()
                        deriving_info["classes"].append(class_name)
        
        return deriving_info

    def extract_instance_component(self, instance_node, src_bytes, import_map):
        """Extract instance declaration components"""
        start, end = instance_node.start_point[0], instance_node.end_point[0]
        instance_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
        
        # Store import_map for use in qualified info extraction
        self.current_import_map = import_map
        
        # Extract instance name and type patterns
        instance_name = self.extract_instance_name(instance_node, src_bytes)
        type_patterns = self.extract_type_patterns(instance_node, src_bytes)
        
        # Extract instance declarations (methods/bindings)
        instance_methods = []
        type_instances = []
        
        # Find instance_declarations node
        for child in instance_node.children:
            if child.type == "instance_declarations":
                for decl in child.children:
                    if decl.type == "declaration":
                        for inner_decl in decl.children:
                            if inner_decl.type == "bind":
                                # Extract method binding
                                method = self.extract_instance_method(inner_decl, src_bytes, import_map)
                                if method:
                                    instance_methods.append(method)
                            elif inner_decl.type == "type_instance":
                                # Extract type instance
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
            "type_instances": type_instances,
            "function_calls": self.extract_function_calls(instance_code, import_map)
        }
        
        return comp

    def extract_instance_name(self, instance_node, src_bytes):
        """Extract the instance name (typeclass name)"""
        # Look for the name field in instance node
        name_node = None
        for child in instance_node.children:
            if child.type == "name":
                name_node = child
                break
        
        if name_node:
            return src_bytes[name_node.start_byte:name_node.end_byte].decode()
        
        # Fallback: extract from the instance line
        first_line = src_bytes.split(b"\n")[instance_node.start_point[0]].decode()
        if "instance" in first_line:
            parts = first_line.split()
            if len(parts) > 1:
                return parts[1]  # First identifier after "instance"
        
        return "UnknownInstance"

    def extract_type_patterns(self, instance_node, src_bytes):
        """Extract type patterns from instance declaration"""
        patterns = []
        
        # Look for type_patterns node
        for child in instance_node.children:
            if child.type == "type_patterns":
                for pattern in child.children:
                    if pattern.type == "qualified":
                        qualified_info = self.extract_qualified_info(pattern, src_bytes)
                        patterns.append(qualified_info)
                    else:
                        # Handle other pattern types
                        pattern_text = src_bytes[pattern.start_byte:pattern.end_byte].decode()
                        patterns.append({
                            'name': pattern_text,
                            'type': 'simple',
                            'context': 'type_pattern'
                        })
        
        return patterns

    def extract_qualified_info(self, qualified_node, src_bytes):
        """Extract qualified name with full info like function calls"""
        module_part = ""
        id_part = ""
        
        for child in qualified_node.children:
            if child.type == "module":
                # Extract module hierarchy
                for module_child in child.children:
                    if module_child.type == "module_id":
                        module_part = src_bytes[module_child.start_byte:module_child.end_byte].decode()
            elif child.type == "name":
                id_part = src_bytes[child.start_byte:child.end_byte].decode()
        
        if module_part and id_part:
            full_name = f"{module_part}.{id_part}"
            # Resolve module through import map
            resolved_modules = [module_part]
            import_map = getattr(self, 'current_import_map', self.import_map)
            if module_part in import_map:
                resolved_modules = import_map[module_part]
            
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
        """Extract method binding from instance"""
        method_name = ""
        method_code = ""
        
        # Extract variable name
        for child in bind_node.children:
            if child.type == "variable":
                method_name = src_bytes[child.start_byte:child.end_byte].decode()
                break
        
        # Extract full method code
        start, end = bind_node.start_point[0], bind_node.end_point[0]
        method_code = b"\n".join(src_bytes.split(b"\n")[start : end + 1]).decode("utf8")
        
        method = {
            "kind": "instance_method",
            "name": method_name,
            "code": method_code.strip(),
            "function_calls": self.extract_function_calls(method_code, import_map)
        }
        
        return method

    def extract_type_instance(self, type_instance_node, src_bytes):
        """Extract type instance declarations (like type ErrResponse = ...)"""
        type_name = ""
        type_patterns = []
        type_definition = ""
        
        # Extract name
        for child in type_instance_node.children:
            if child.type == "name":
                type_name = src_bytes[child.start_byte:child.end_byte].decode()
                break
        
        # Extract type patterns
        for child in type_instance_node.children:
            if child.type == "type_patterns":
                for pattern in child.children:
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
        
        # Extract type definition (the part after =)
        # Look for the last child which should be the type definition
        last_child = type_instance_node.children[-1] if type_instance_node.children else None
        if last_child and last_child.type in ["qualified", "unit"]:
            if last_child.type == "qualified":
                type_definition = self.extract_qualified_info(last_child, src_bytes)
            else:
                type_definition = {
                    'name': src_bytes[last_child.start_byte:last_child.end_byte].decode(),
                    'type': 'simple',
                    'context': 'type_definition'
                }
        
        return {
            "kind": "type_instance",
            "name": type_name,
            "type_patterns": type_patterns,
            "type_definition": type_definition
        }

    def extract_function_calls(self, func_code: str, import_map: dict):
        lines = func_code.split('\n')
        identifiers = []

        string_pattern = re.compile(r'"(?:[^"\\]|\\.)*"')
        operator_pattern = re.compile(r'\((\S+)\)')
        qualified_name_pattern = re.compile(r'\b((?:[A-Z][a-zA-Z0-9_]*\.)*)([A-Z][a-zA-Z0-9_]*\.)?([a-z][a-zA-Z0-9_\']*)\b')
        list_pattern = re.compile(r'\[(.*?)\]')
        tuple_pattern = re.compile(r'\(([^)]*,.*?)\)')
        record_pattern = re.compile(r'\{(.*?)\}')
        lambda_pattern = re.compile(r'\\[^>]+->')
        numeric_literal_pattern = re.compile(r'\b\d+(?:\.\d+)?\b')

        # Remove collection patterns that are causing false positives
        collection_patterns = {
            'Map': ['lookup', 'insert', 'delete', 'fromList', 'toList'],
            'Set': ['fromList', 'toList', 'union', 'difference']
            # Removed Seq patterns that were causing |> and <| false matches
        }

        for line in lines:
            line = re.sub(r'--.*', '', line)
            line = string_pattern.sub('', line)

            # Skip type signature lines and instance/where keywords
            if '::' in line or line.strip().startswith('instance') or line.strip().startswith('where'):
                continue

            for match in qualified_name_pattern.finditer(line):
                prefix = (match.group(1) or match.group(2) or '').rstrip('.')
                base_name = match.group(3)
                if not prefix:
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

            operators = operator_pattern.findall(line)
            for op in operators:
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

            # Only extract type constructors from non-type-signature lines
            for ctor in re.findall(r'\b([A-Z][a-zA-Z0-9_\']*)\b', line):
                # Skip common keywords
                if ctor not in ['type', 'instance', 'where', 'data', 'newtype']:
                    identifiers.append({
                        'name': ctor,
                        'type': 'type_constructor',
                        'context': 'type_system'
                    })

            for call in re.findall(r'\b([a-z][a-zA-Z0-9_\']*)\s*(?=\()', line):
                identifiers.append({
                    'name': call,
                    'type': 'function',
                    'context': 'function_call'
                })

            # Only extract variables from assignment lines, not type signatures or keywords
            if '=' in line and 'type' not in line:
                for var in re.findall(r'\b([a-z][a-zA-Z0-9_\']*)\b', line):
                    # Skip common keywords
                    if var not in ['instance', 'where', 'type', 'data', 'newtype', 'let', 'in', 'do', 'case', 'of']:
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

    def extract_where_definitions(self, func_code: str):
        lines = func_code.split("\n")
        where_idx = None
        where_indent = 0

        for idx, line in enumerate(lines):
            if re.match(r"\s*where\b", line):
                where_idx = idx
                where_indent = len(line) - len(line.lstrip())
                break
        if where_idx is None:
            return []

        decl_lines = []
        for line in lines[where_idx + 1 :]:
            if not line.strip():
                decl_lines.append(line)
                continue
            indent = len(line) - len(line.lstrip())
            if indent > where_indent:
                decl_lines.append(line[where_indent + 1 :])
            else:
                break

        chunks = []
        current = []
        for line in decl_lines:
            if not line.strip() and current:
                chunks.append(current)
                current = []
            elif line.strip():
                current.append(line)
        if current:
            chunks.append(current)

        defs = []
        for chunk in chunks:
            snippet = "\n".join(chunk).rstrip()
            first = chunk[0].lstrip()
            if "::" in first:
                kind = "signature"
                name = first.split("::", 1)[0].strip()
            else:
                kind = "function"
                name = first.split()[0].split("(")[0]
            defs.append({
                "kind": kind,
                "name": name,
                "code": snippet,
            })
        return defs

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

    def extract_all_components(self):
        raw_groups = [self.extract_top_level_components(i, self.src, self.import_map) for i in self.tree.root_node.children]
        all_components = [c for group in raw_groups for c in group]
        for comp in all_components:
            if comp["kind"] == "function":
                fn_name = comp["code"].split()[0].split("(")[0]
                comp["type_dependencies"] = self.find_type_dependencies(fn_name, all_components)
        return all_components