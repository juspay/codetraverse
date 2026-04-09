import os
import re
import tree_sitter_java
from tree_sitter import Language, Parser, Node
import json
from collections import defaultdict
from codetraverse.base.component_extractor import ComponentExtractor


def get_node_text(node, src):
    return src[node.start_byte:node.end_byte].decode(errors="ignore")


def find_package(root, src):
    """Find the package declaration in the Java file."""
    for node in root.children:
        if node.type == "package_declaration":
            for child in node.children:
                if child.type == "scoped_identifier":
                    return get_node_text(child, src)
            for child in node.named_children:
                if child.type == "scoped_identifier":
                    return get_node_text(child, src)
    return None


def find_imports(root, src):
    """Find all import declarations in the Java file."""
    imports = []
    for node in root.children:
        if node.type == "import_declaration":
            import_text = ""
            for child in node.children:
                if child.type not in ("semi", ";"):
                    import_text += get_node_text(child, src)
            import_text = import_text.strip()
            if import_text:
                imports.append(import_text)
    return imports


def extract_doc_comment(node, src):
    """Extract Javadoc-style comment before a declaration."""
    siblings = node.parent.children if node.parent else []
    try:
        idx = siblings.index(node)
    except ValueError:
        return None
    
    doc = ""
    for i in range(idx - 1, -1, -1):
        sib = siblings[i]
        if sib.type in ("comment", "line_comment", "block_comment"):
            comment_text = get_node_text(sib, src).strip()
            # Remove common comment prefixes
            comment_text = re.sub(r'^/\*\*?\s*', '', comment_text)
            comment_text = re.sub(r'^[\s*]+', '', comment_text)
            comment_text = comment_text.strip('*/ ')
            doc = comment_text + "\n" + doc
        else:
            break
    return doc.strip() if doc else None


def find_class_doc_comment(node, src):
    """Find doc comment specifically for classes (handles Javadoc format)."""
    siblings = node.parent.children if node.parent else []
    try:
        idx = siblings.index(node)
    except ValueError:
        return None
    
    # Look for Javadoc (/** ... */) before the class
    for i in range(idx - 1, -1, -1):
        sib = siblings[i]
        if sib.type == "comment":
            text = get_node_text(sib, src).strip()
            if text.startswith("/**"):
                # This is a Javadoc comment
                text = re.sub(r'^/\*\*', '', text)
                text = re.sub(r'\*/$', '', text)
                text = re.sub(r'^\s*\*\s?', '', text, flags=re.MULTILINE)
                return text.strip()
            elif text.startswith("//"):
                continue
            else:
                break
        elif sib.type not in ("annotation", "line_comment"):
            break
    return None


class JavaComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.JAVA_LANGUAGE = Language(tree_sitter_java.language())
        self.parser = Parser(self.JAVA_LANGUAGE)
        self.imports = []
        self.package_name = ""
        self.all_components = []
        self.class_methods = defaultdict(list)
        self.current_file_path = ""
        self.repo_root = ""
        self.qualified_name = ""

    def process_file(self, file_path):
        self.current_file_path = file_path
        self.repo_root = self._find_repo_root(file_path)
        
        with open(file_path, "rb") as f:
            src = f.read()
        
        tree = self.parser.parse(src)
        root = tree.root_node
        
        # Extract package and imports
        self.package_name = find_package(root, src)
        self.imports = find_imports(root, src)
        
        # Build qualified name for the file
        file_name = os.path.basename(file_path)
        class_name = os.path.splitext(file_name)[0]
        if self.package_name:
            self.qualified_name = f"{self.package_name}.{class_name}"
        else:
            self.qualified_name = class_name
        
        # Collect class documentation
        class_docs = {}
        for node in root.children:
            if node.type in ("class_declaration", "interface_declaration", "enum_declaration"):
                doc = find_class_doc_comment(node, src)
                for child in node.named_children:
                    if child.type == "identifier":
                        name = get_node_text(child, src)
                        class_docs[name] = doc
                        break
        
        # Start building components with file info
        self.all_components = [{
            "kind": "file",
            "file_docstring": "",
            "package": self.package_name,
            "imports": self.imports,
            "file_path": os.path.relpath(file_path, start=self.repo_root) if self.repo_root else file_path,
        }]
        
        self.class_methods = defaultdict(list)
        
        # Process all declarations
        for node in root.children:
            if node.type == "class_declaration":
                self._process_class_declaration(node, src, class_docs)
            elif node.type == "interface_declaration":
                self._process_interface_declaration(node, src, class_docs)
            elif node.type == "enum_declaration":
                self._process_enum_declaration(node, src, class_docs)
            elif node.type in ("method_declaration", "constructor_declaration"):
                method = self._process_method(node, src)
                if method:
                    self.all_components.append(method)
        
        # Attach methods to classes
        for comp in self.all_components:
            if comp.get("kind") in ("class", "interface", "enum"):
                comp["methods"] = self.class_methods.get(comp.get("name"), [])

    def _find_repo_root(self, file_path):
        """Find the repository root by looking for build files."""
        curr = os.path.abspath(file_path)
        markers = ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", ".git"]
        while curr != os.path.dirname(curr):
            for marker in markers:
                if os.path.isfile(os.path.join(curr, marker)):
                    return curr
            curr = os.path.dirname(curr)
        return os.path.dirname(file_path)

    def write_to_file(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.all_components

    def _get_method_signature(self, name, params, param_types, return_type, is_constructor=False):
        """Build a method signature string."""
        params_sig = ", ".join(
            f"{p} {param_types[p]}" if p in param_types else p
            for p in params
        )
        if is_constructor:
            return f"{name}({params_sig})"
        ret = f" {return_type}" if return_type else ""
        return f"{name}({params_sig}){ret}"

    def _function_complete_path(self, name, class_name=None, is_constructor=False):
        """Build a complete path for the method."""
        file_path_rel = self.current_file_path
        if self.repo_root:
            file_path_rel = os.path.relpath(self.current_file_path, start=self.repo_root)
        file_path_rel = file_path_rel.replace(os.sep, ".").replace("/", ".")
        
        if class_name:
            return f"{file_path_rel}.{class_name}.{name}"
        return f"{file_path_rel}.{name}"

    def _process_method(self, node: Node, src, class_name=None):
        """Process a method or constructor declaration."""
        is_constructor = node.type == "constructor_declaration"
        
        # Get method name
        name = None
        for child in node.children:
            if child.type == "identifier":
                name = get_node_text(child, src)
                break
        
        if not name:
            return None
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = get_node_text(node, src)
        doc = extract_doc_comment(node, src)
        
        # Get parameters
        params = []
        param_types = {}
        param_list = node.child_by_field_name("parameters")
        if param_list:
            for p in param_list.named_children:
                if p.type == "parameter":
                    # Get parameter name
                    pname = None
                    ptype = None
                    for child in p.children:
                        if child.type == "identifier":
                            pname = get_node_text(child, src)
                        elif child.type in ("type_identifier", "scoped_type_identifier", "array_type", "generic_type"):
                            ptype = get_node_text(child, src)
                    if pname:
                        params.append(pname)
                        if ptype:
                            param_types[pname] = ptype
        
        # Get return type
        return_type = None
        if not is_constructor:
            result_node = node.child_by_field_name("type")
            if result_node:
                return_type = get_node_text(result_node, src)
        
        # Track method in class
        if class_name:
            self.class_methods[class_name].append(name)
        
        # Extract function calls, literals, variables
        calls, literals, variables, type_deps = [], [], [], set()
        
        def walk(n):
            if n.type == "method_invocation":
                # Get method call name
                for child in n.children:
                    if child.type == "identifier":
                        calls.append(get_node_text(child, src))
                        break
                    elif child.type == "member_expression":
                        # Handle this.method() or obj.method()
                        member = n.child_by_field_name("member")
                        if member:
                            calls.append(get_node_text(member, src))
                        break
            elif n.type == "object_creation_expression":
                # Handle new ClassName()
                for child in n.children:
                    if child.type == "type_identifier":
                        calls.append(f"new {get_node_text(child, src)}")
                        break
            elif n.type in ("string_literal", "decimal_integer_literal", 
                           "hex_integer_literal", "octal_integer_literal",
                           "binary_integer_literal", "decimal_floating_point_literal",
                           "boolean_literal", "null_literal"):
                literals.append(get_node_text(n, src))
            elif n.type == "variable_declarator":
                # Local variable declaration
                var_name = None
                var_value = None
                for child in n.named_children:
                    if child.type == "identifier":
                        var_name = get_node_text(child, src)
                    elif child.type not in ("type_identifier", "array_type", "generic_type"):
                        var_value = get_node_text(child, src)
                if var_name:
                    variables.append({"name": var_name, "value": var_value})
            elif n.type in ("type_identifier", "scoped_type_identifier"):
                t = get_node_text(n, src)
                if t and t[0].isupper():
                    type_deps.add(t)
            for child in n.children:
                walk(child)
        
        body = node.child_by_field_name("body")
        if body:
            walk(body)
        
        complete_path = self._function_complete_path(name, class_name, is_constructor)
        kind = "constructor" if is_constructor else "method"
        
        return {
            "kind": kind,
            "name": name,
            "complete_function_path": complete_path,
            "start_line": start_line,
            "end_line": end_line,
            "doc_comment": doc,
            "parameters": params,
            "parameter_types": param_types,
            "return_type": return_type,
            "receiver_type": class_name,
            "variables": variables,
            "literals": literals,
            "function_calls": calls,
            "type_dependencies": list(type_deps),
            "code": code,
            "imports": self.imports,
            "package": self.package_name,
            "file_path": os.path.relpath(self.current_file_path, start=self.repo_root) if self.repo_root else self.current_file_path,
        }

    def _process_class_declaration(self, node: Node, src, class_docs):
        """Process a class declaration."""
        class_name = None
        extends_name = None
        implements_names = []
        
        for child in node.named_children:
            if child.type == "identifier":
                class_name = get_node_text(child, src)
            elif child.type == "extends_clause":
                for c in child.children:
                    if c.type in ("type_identifier", "scoped_type_identifier"):
                        extends_name = get_node_text(c, src)
            elif child.type == "implements_clause":
                for c in child.children:
                    if c.type in ("type_identifier", "scoped_type_identifier"):
                        implements_names.append(get_node_text(c, src))
        
        if not class_name:
            return
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = get_node_text(node, src)
        doc = class_docs.get(class_name)
        
        # Extract fields
        fields = []
        field_types = set()
        
        class_body = node.child_by_field_name("body")
        if class_body:
            for member in class_body.children:
                if member.type == "field_declaration":
                    field_names = []
                    field_type = None
                    for child in member.children:
                        if child.type == "variable_declarator":
                            for c in child.children:
                                if c.type == "identifier":
                                    field_names.append(get_node_text(c, src))
                        elif child.type in ("type_identifier", "scoped_type_identifier", 
                                           "array_type", "generic_type", "primitive_type"):
                            field_type = get_node_text(child, src)
                    
                    for fname in field_names:
                        fields.append({"name": fname, "type": field_type})
                    if field_type:
                        field_types.add(field_type)
                elif member.type in ("method_declaration", "constructor_declaration"):
                    method = self._process_method(member, src, class_name)
                    if method:
                        self.all_components.append(method)
        
        class_comp = {
            "kind": "class",
            "name": class_name,
            "extends": extends_name,
            "implements": implements_names,
            "start_line": start_line,
            "end_line": end_line,
            "doc_comment": doc,
            "fields": fields,
            "field_types": list(field_types),
            "methods": [],
            "code": code,
            "imports": self.imports,
            "package": self.package_name,
            "file_path": os.path.relpath(self.current_file_path, start=self.repo_root) if self.repo_root else self.current_file_path,
        }
        self.all_components.append(class_comp)

    def _process_interface_declaration(self, node: Node, src, class_docs):
        """Process an interface declaration."""
        interface_name = None
        extends_names = []
        
        for child in node.named_children:
            if child.type == "identifier":
                interface_name = get_node_text(child, src)
            elif child.type == "extends_clause":
                for c in child.children:
                    if c.type in ("type_identifier", "scoped_type_identifier"):
                        extends_names.append(get_node_text(c, src))
        
        if not interface_name:
            return
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = get_node_text(node, src)
        doc = class_docs.get(interface_name)
        
        # Extract interface methods
        methods = []
        
        interface_body = node.child_by_field_name("body")
        if interface_body:
            for member in interface_body.children:
                if member.type == "method_declaration":
                    method_name = None
                    return_type = None
                    params = []
                    param_types = {}
                    
                    for child in member.children:
                        if child.type == "identifier":
                            method_name = get_node_text(child, src)
                        elif child.type == "type_identifier":
                            return_type = get_node_text(child, src)
                    
                    param_list = member.child_by_field_name("parameters")
                    if param_list:
                        for p in param_list.named_children:
                            if p.type == "parameter":
                                pname = None
                                ptype = None
                                for c in p.children:
                                    if c.type == "identifier":
                                        pname = get_node_text(c, src)
                                    elif c.type in ("type_identifier", "scoped_type_identifier"):
                                        ptype = get_node_text(c, src)
                                if pname:
                                    params.append(pname)
                                    if ptype:
                                        param_types[pname] = ptype
                    
                    methods.append({
                        "name": method_name,
                        "parameters": params,
                        "parameter_types": param_types,
                        "return_type": return_type,
                    })
                    
                    # Also add as a full method component
                    method_comp = self._process_method(member, src, interface_name)
                    if method_comp:
                        self.all_components.append(method_comp)
        
        self.all_components.append({
            "kind": "interface",
            "name": interface_name,
            "extends": extends_names,
            "start_line": start_line,
            "end_line": end_line,
            "doc_comment": doc,
            "methods": methods,
            "code": code,
            "imports": self.imports,
            "package": self.package_name,
            "file_path": os.path.relpath(self.current_file_path, start=self.repo_root) if self.repo_root else self.current_file_path,
        })

    def _process_enum_declaration(self, node: Node, src, class_docs):
        """Process an enum declaration."""
        enum_name = None
        implements_names = []
        
        for child in node.named_children:
            if child.type == "identifier":
                enum_name = get_node_text(child, src)
            elif child.type == "implements_clause":
                for c in child.children:
                    if c.type in ("type_identifier", "scoped_type_identifier"):
                        implements_names.append(get_node_text(c, src))
        
        if not enum_name:
            return
        
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        code = get_node_text(node, src)
        doc = class_docs.get(enum_name)
        
        # Extract enum constants
        constants = []
        enum_body = node.child_by_field_name("body")
        if enum_body:
            for member in enum_body.children:
                if member.type == "enum_constant_declaration":
                    for child in member.named_children:
                        if child.type == "identifier":
                            constants.append(get_node_text(child, src))
                            break
                elif member.type == "method_declaration":
                    method = self._process_method(member, src, enum_name)
                    if method:
                        self.all_components.append(method)
        
        self.all_components.append({
            "kind": "enum",
            "name": enum_name,
            "implements": implements_names,
            "constants": constants,
            "start_line": start_line,
            "end_line": end_line,
            "doc_comment": doc,
            "methods": [],
            "code": code,
            "imports": self.imports,
            "package": self.package_name,
            "file_path": os.path.relpath(self.current_file_path, start=self.repo_root) if self.repo_root else self.current_file_path,
        })