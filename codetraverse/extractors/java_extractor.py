# codetraverse/extractors/java_extractor.py

import os
import json
from tree_sitter_language_pack import get_parser
from codetraverse.base.component_extractor import ComponentExtractor


class JavaComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.parser = get_parser("java")
        self.all_components = []
        self.imports = {}

    def parse_file(self, file_path: str):
        with open(file_path, 'r', encoding='utf-8') as f:
            plain = f.read()
        tree = self.parser.parse(plain.encode("utf8"))
        return plain, tree

    def get_text(self, node, plain: str) -> str:
        b = plain.encode("utf8")
        return b[node.start_byte:node.end_byte].decode("utf8", errors="replace")

    def extract_annotations(self, node, plain):
        annotations = []
        
        # Check direct children
        for child in node.children:
            if child.type == "annotation":
                ann_name = self.get_text(child, plain).strip()
                if ann_name.startswith('@'):
                    ann_name = ann_name[1:]
                annotations.append(ann_name)
        
        # Check modifiers node (which contains annotations in Java) - iterate by type
        for child in node.children:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type == "annotation":
                        ann_name = self.get_text(mod_child, plain).strip()
                        if ann_name.startswith('@'):
                            ann_name = ann_name[1:]
                        if ann_name not in annotations:
                            annotations.append(ann_name)
        
        return annotations if annotations else None

    def extract_jackson_annotations(self, node, plain):
        jackson_meta = {}
        
        annotations = self.extract_annotations(node, plain)
        if not annotations:
            return None
            
        for ann in annotations:
            ann_lower = ann.lower()
            
            # @JsonInclude
            if "jsoninclude" in ann_lower:
                match = ann.split('(')[1].split(')')[0] if '(' in ann else ""
                jackson_meta["json_include"] = match.strip()
            
            # @JsonIgnoreProperties
            elif "jsonignoreproperties" in ann_lower:
                match = ann.split('(')[1].split(')')[0] if '(' in ann else ""
                jackson_meta["json_ignore_properties"] = match.strip()
        
        # Check for field-level Jackson annotations
        for child in node.children:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type == "annotation":
                        ann_text = self.get_text(mod_child, plain).strip()
                        
                        # @JsonProperty
                        if "jsonproperty" in ann_text.lower():
                            match = ann_text.split('(')[1].split(')')[0] if '(' in ann_text else ""
                            jackson_meta["json_property"] = match.strip()
                        
                        # @JsonIgnore
                        elif "jsonignore" in ann_text.lower():
                            jackson_meta["json_ignore"] = True
                        
                        # @JsonAlias
                        elif "jsonalias" in ann_text.lower():
                            match = ann_text.split('(')[1].split(')')[0] if '(' in ann_text else ""
                            jackson_meta["json_alias"] = match.strip()
        
        return jackson_meta if jackson_meta else None

    def _extract_step_pattern(self, node, plain, annotation_name):
        def find_string_in_annotation(ann_node):
            for child in ann_node.children:
                if child.type == "annotation_argument_list":
                    for inner in child.children:
                        if inner.type == "string_literal":
                            content = self.get_text(inner, plain)
                            if content.startswith('"') and content.endswith('"'):
                                return content[1:-1]
                            return content
            return None
        
        # Get the base annotation name (Given, When, Then)
        base_name = annotation_name.split('(')[0].strip()
        
        # Check direct children
        for child in node.children:
            if child.type == "annotation":
                ann_text = self.get_text(child, plain).strip()
                ann_base = ann_text.split('(')[0].strip()
                if ann_base.startswith('@'):
                    ann_base = ann_base[1:]
                if base_name.lower() == ann_base.lower():
                    pattern = find_string_in_annotation(child)
                    if pattern:
                        return pattern
        
        # Check modifiers node - iterate by type
        for c in node.children:
            if c.type == "modifiers":
                for child in c.children:
                    if child.type == "annotation":
                        ann_text = self.get_text(child, plain).strip()
                        ann_base = ann_text.split('(')[0].strip()
                        if ann_base.startswith('@'):
                            ann_base = ann_base[1:]
                        if base_name.lower() == ann_base.lower():
                            pattern = find_string_in_annotation(child)
                            if pattern:
                                return pattern
        return None

    def extract_parameters(self, node, plain):
        params = []
        
        # Find formal_parameters by iterating children
        formal_params = None
        for child in node.children:
            if child.type == "formal_parameters":
                formal_params = child
                break
        
        if not formal_params:
            return None
            
        for child in formal_params.children:
            if child.type == "formal_parameter":
                param_name = None
                param_type = None
                for pc in child.children:
                    if pc.type == "identifier":
                        param_name = self.get_text(pc, plain)
                    elif pc.type in ("type_identifier", "primitive_type"):
                        param_type = self.get_text(pc, plain)
                if param_name:
                    params.append({"name": param_name, "type": param_type})
        return params if params else None

    def extract_extends_implements(self, node, plain):
        extends = None
        implements = None
        
        for child in node.children:
            if child.type == "superclass":
                extends_text = self.get_text(child, plain).strip()
                extends = extends_text.replace("extends", "").strip() if extends_text else None
            elif child.type == "super_interfaces":
                implements_text = self.get_text(child, plain).strip()
                implements = implements_text.replace("implements", "").strip() if implements_text else None
        
        return extends, implements

    def extract_method_calls(self, node, plain, module_name, rel_path):
        calls = []
        
        def visit(n):
            if n.type == "method_invocation":
                method = n.child_by_field_name("method")
                if method:
                    method_name = self.get_text(method, plain).strip()
                    calls.append({
                        "name": method_name,
                        "base_name": method_name.split(".")[-1] if "." in method_name else method_name,
                        "resolved_callee": f"{rel_path}::{method_name}"
                    })
            for c in n.children:
                visit(c)
        
        visit(node)
        return calls

    def extract_field_declarators(self, node, plain):
        fields = []
        for child in node.named_children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    fields.append(self.get_text(name_node, plain))
        return fields if fields else None

    def walk_node(self, node, plain, file_path, root_folder, rel_path):
        comps = []
        module_name = os.path.relpath(file_path, root_folder).replace("\\", "/")

        # Package declaration
        if node.type == "package_declaration":
            for child in node.named_children:
                if child.type == "scoped_identifier":
                    pkg = self.get_text(child, plain)
                    comps.append({
                        "kind": "package",
                        "module": module_name,
                        "name": pkg,
                        "code": self.get_text(node, plain),
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                    })

        # Import declarations
        if node.type == "import_declaration":
            code = self.get_text(node, plain).strip()
            if code.startswith("import"):
                parts = code.split()
                if len(parts) >= 2:
                    imported = parts[1].rstrip(';')
                    is_static = "static" in parts
                    comps.append({
                        "kind": "import",
                        "module": module_name,
                        "name": imported,
                        "static": is_static,
                        "code": code,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                    })

        # Class declarations
        if node.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            name_node = node.child_by_field_name("name")
            class_name = self.get_text(name_node, plain) if name_node else "<anon>"
            
            annotations = self.extract_annotations(node, plain)
            jackson_meta = self.extract_jackson_annotations(node, plain)
            extends, implements = self.extract_extends_implements(node, plain)
            
            kind_map = {
                "class_declaration": "class",
                "interface_declaration": "interface", 
                "enum_declaration": "enum"
            }
            
            comp = {
                "kind": kind_map.get(node.type, "class"),
                "module": module_name,
                "name": class_name,
                "annotations": annotations,
                "extends": extends,
                "implements": implements,
                "code": self.get_text(node, plain),
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
            }
            
            if jackson_meta:
                comp["jackson"] = jackson_meta
            
            comps.append(comp)

            # Process body declarations (methods, fields, constructors, nested classes)
            body = node.child_by_field_name("body")
            if body:
                for decl in body.named_children:
                    # Methods
                    if decl.type in ("method_declaration", "constructor_declaration"):
                        self._process_method(decl, plain, module_name, class_name, rel_path, comps)
                    
                    # Field declarations
                    elif decl.type == "field_declaration":
                        self._process_field(decl, plain, module_name, class_name, comps)
                    
                    # Nested classes
                    elif decl.type in ("class_declaration", "interface_declaration", "enum_declaration"):
                        nested_comps = self.walk_node(decl, plain, file_path, root_folder, rel_path)
                        for nc in nested_comps:
                            if nc.get("kind") in ("class", "interface", "enum"):
                                nc["enclosing_class"] = class_name
                        comps.extend(nested_comps)

        # Standalone methods (not inside a class)
        if node.type in ("method_declaration", "constructor_declaration"):
            # Check if this is a top-level method (not inside a class)
            parent = node.parent
            if parent and parent.type not in ("class_declaration", "interface_declaration", "enum_declaration", "program"):
                self._process_method(node, plain, module_name, None, rel_path, comps)

        # Recurse
        for child in node.children:
            comps.extend(self.walk_node(child, plain, file_path, root_folder, rel_path))

        return comps

    def _process_method(self, node, plain, module_name, class_name, rel_path, comps):
        name_node = node.child_by_field_name("name")
        method_name = self.get_text(name_node, plain) if name_node else "<init>"
        
        annotations = self.extract_annotations(node, plain)
        params = self.extract_parameters(node, plain)
        
        # Return type for methods (not constructors)
        return_type = None
        if node.type == "method_declaration":
            type_node = node.child_by_field_name("type")
            if type_node:
                return_type = self.get_text(type_node, plain)
        
        is_static = any("static" in str(a).lower() for a in (annotations or []))
        
        calls = self.extract_method_calls(node, plain, module_name, rel_path)
        
        kind = "constructor" if node.type == "constructor_declaration" else "method"
        
        step_type = None
        step_pattern = None
        
        if annotations:
            for ann in annotations:
                ann_lower = ann.lower()
                if ann_lower.startswith("given"):
                    step_type = "given"
                    step_pattern = self._extract_step_pattern(node, plain, ann)
                    kind = "step_definition"
                    break
                elif ann_lower.startswith("when"):
                    step_type = "when"
                    step_pattern = self._extract_step_pattern(node, plain, ann)
                    kind = "step_definition"
                    break
                elif ann_lower.startswith("then"):
                    step_type = "then"
                    step_pattern = self._extract_step_pattern(node, plain, ann)
                    kind = "step_definition"
                    break
        
        comp = {
            "kind": kind,
            "module": module_name,
            "name": method_name,
            "annotations": annotations,
            "parameters": params,
            "returns": return_type,
            "static": is_static,
            "code": self.get_text(node, plain),
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "function_calls": calls
        }
        
        if step_type:
            comp["step_type"] = step_type
        if step_pattern:
            comp["step_pattern"] = step_pattern
        
        if class_name:
            comp["class"] = class_name
        
        comps.append(comp)

    def _process_field(self, node, plain, module_name, class_name, comps):
        annotations = self.extract_annotations(node, plain)
        jackson_meta = self.extract_jackson_annotations(node, plain)
        
        # Get field type
        type_node = node.child_by_field_name("type")
        field_type = self.get_text(type_node, plain) if type_node else None
        
        # Get variable declarators
        declarators = node.child_by_field_name("declarators")
        if declarators:
            for decl in declarators.named_children:
                if decl.type == "variable_declarator":
                    name_node = decl.child_by_field_name("name")
                    field_name = self.get_text(name_node, plain) if name_node else None
                    
                    if field_name:
                        comp = {
                            "kind": "field",
                            "module": module_name,
                            "name": field_name,
                            "type": field_type,
                            "annotations": annotations,
                            "class": class_name,
                            "code": self.get_text(node, plain),
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                        }
                        if jackson_meta:
                            comp["jackson"] = jackson_meta
                        comps.append(comp)

    def extract_from_file(self, filepath, root_folder, rel_path):
        plain, tree = self.parse_file(filepath)
        return self.walk_node(tree.root_node, plain, filepath, root_folder, rel_path)

    def extract_from_folder(self, folder):
        out = []
        project_root = os.environ.get("ROOT_DIR", "")
        abs_folder = os.path.abspath(folder)
        for root, _, files in os.walk(abs_folder):
            for f in files:
                if f.endswith('.java'):
                    file_path = os.path.join(root, f)
                    rel = os.path.relpath(file_path, project_root).replace(os.sep, "/")
                    comps = self.extract_from_file(file_path, abs_folder, rel)
                    for c in comps:
                        c["file_path"] = rel
                        c.setdefault("module", rel)
                    out.extend(comps)
        return out

    def process_file(self, file_path: str):
        plain, tree = self.parse_file(file_path)
        root_folder = os.path.dirname(file_path)
        
        project_root = os.environ.get("ROOT_DIR", "")
        rel = os.path.relpath(file_path, project_root).replace(os.sep, "/")
        
        raw = self.extract_from_file(file_path, root_folder, rel)
        
        # Build import map
        self.imports = {}
        for comp in raw:
            if comp.get("kind") == "import":
                name = comp.get("name", "")
                if name:
                    self.imports[name.split(".")[-1]] = name
                    self.imports[name] = name
        
        # Add file_path to each component
        for c in raw:
            c["file_path"] = rel
            c.setdefault("module", rel)
        
        # Filter JSON-serializable
        self.all_components = [c for c in raw if self._is_jsonable(c)]

    def _is_jsonable(self, x):
        try:
            json.dumps(x)
            return True
        except Exception:
            return False

    def write_to_file(self, output_path: str):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.all_components
