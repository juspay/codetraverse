import tree_sitter_haskell
from tree_sitter import Language, Parser, Node
import json
import re
from collections import defaultdict
from codetraverse.base.component_extractor import ComponentExtractor

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
        return components

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

        collection_patterns = {
            'Map': ['lookup', 'insert', 'delete', 'fromList', 'toList'],
            'Set': ['fromList', 'toList', 'union', 'difference'],
            'Seq': ['empty', '<|', '|>', 'fromList']
        }

        for line in lines:
            line = re.sub(r'--.*', '', line)
            line = string_pattern.sub('', line)

            if '::' in line:
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

            for ctor in re.findall(r'\b([A-Z][a-zA-Z0-9_\']*)\b', line):
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

            for var in re.findall(r'\b([a-z][a-zA-Z0-9_\']*)\b', line):
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
