import os
import json
import tree_sitter_typescript
from tree_sitter import Language, Parser

# Import your base class. Adjust as necessary for your environment.
from base.component_extractor import ComponentExtractor

class TypeScriptComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.language = Language(tree_sitter_typescript.language_typescript())
        self.parser = Parser(self.language)
        self.all_components = []

    def parse_file(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        tree = self.parser.parse(bytes(code, 'utf8'))
        return code, tree

    def get_text(self, node, code):
        return code[node.start_byte:node.end_byte]

    def extract_ident(self, node, code):
        for c in node.children:
            if c.type in ('identifier', 'type_identifier', 'property_identifier'):
                return self.get_text(c, code)
        return None

    def parse_imports(self, node, code):
        """Returns a dict mapping imported names to their source modules."""
        imports = {}
        if node.type == 'import_statement':
            text = self.get_text(node, code)
            if 'from' in text:
                parts = text.split('from')
                left = parts[0]
                right = parts[1].strip().strip(';').strip("'\"")
                right = right.strip("'\"")
                if '{' in left:
                    names = left.split('{')[1].split('}')[0]
                    names = [n.strip() for n in names.split(',')]
                    for n in names:
                        if ' as ' in n:
                            orig, alias = [x.strip() for x in n.split(' as ')]
                            imports[alias] = right
                        else:
                            imports[n] = right
        for c in node.children:
            imports.update(self.parse_imports(c, code))
        return imports

    def collect_imports_for_file(self, root_node, code):
        imports = {}
        for child in root_node.children:
            if child.type == 'import_statement':
                imports.update(self.parse_imports(child, code))
        return imports

    def extract_type_annotation(self, node, code):
        for c in node.children:
            if c.type == 'type_annotation':
                return self.get_text(c, code)
            if c.type == 'type':
                return self.get_text(c, code)
        return None

    def extract_enum_members(self, node, code):
        members = []
        for c in node.children:
            if c.type == "enum_body":
                for cc in c.children:
                    if cc.type in ("enum_assignment", "property_identifier", "identifier"):
                        member_name = None
                        member_value = None
                        for sub in cc.children:
                            if sub.type in ("property_identifier", "identifier"):
                                member_name = self.get_text(sub, code)
                            elif sub.type not in ("=", ":"):
                                member_value = self.get_text(sub, code)
                        if member_name:
                            members.append({"name": member_name, "value": member_value})
        return members

    def extract_modifiers(self, node):
        mods = {"static": False, "abstract": False, "readonly": False, "override": False}
        for c in node.children:
            if c.type in mods:
                mods[c.type] = True
        return mods

    def extract_type_param_constraints(self, node, code):
        constraints = []
        for c in node.children:
            if c.type == "type_parameters":
                for param in c.children:
                    if param.type == "type_parameter":
                        for child in param.children:
                            if child.type == "constraint":
                                constraints.append(self.get_text(child, code))
        return constraints
    def extract_generic_type_dependencies(self, node, code):
        """Return all dependencies from a generic_type node (e.g. Partial<User>)."""
        deps = []
        name = None
        type_args = []
        for c in node.children:
            if c.type == "type_identifier":
                name = self.get_text(c, code)
            elif c.type == "type_arguments":
                for arg in c.children:
                    # Each argument can itself be a generic_type, literal_type, etc.
                    if arg.type != ",":
                        type_args.append(self.get_text(arg, code))
        if name:
            deps.append(name)
        deps += type_args
        return deps
    def extract_lookup_type_dependencies(self, node, code):
        """For lookup_type nodes, get dependencies e.g. User['id'] -> User, 'id'."""
        deps = []
        for c in node.children:
            if c.type in ("type_identifier", "literal_type"):
                deps.append(self.get_text(c, code))
            elif c.type == "lookup_type":
                # nested indexed access
                deps += self.extract_lookup_type_dependencies(c, code)
        return deps
    def extract_conditional_type_dependencies(self, node, code):
        """For conditional_type nodes, collect all involved types/literals."""
        deps = []
        for c in node.children:
            if c.type in ("type_identifier", "predefined_type", "literal_type"):
                deps.append(self.get_text(c, code))
            elif c.type in ("consequence", "alternative", "left", "right"):
                # Children of consequence/alternative/left/right can be literal_type etc.
                for cc in c.children:
                    if cc.type in ("type_identifier", "predefined_type", "literal_type"):
                        deps.append(self.get_text(cc, code))
        return deps
    def extract_mapped_type_dependencies(self, node, code):
        """For mapped_type_clause, extract referenced types, e.g. P in keyof T."""
        deps = []
        for c in node.children:
            if c.type == "type_identifier":
                deps.append(self.get_text(c, code))
            elif c.type == "index_type_query": # e.g., keyof T
                for cc in c.children:
                    if cc.type == "type_identifier":
                        deps.append(self.get_text(cc, code))
        return deps



    def extract_index_signatures(self, node, code):
        indices = []
        for c in node.children:
            if c.type == "index_signature":
                indices.append(self.get_text(c, code))
        return indices

    def extract_decorators(self, node, code):
        decorators = []
        for c in node.children:
            if c.type == 'decorator':
                decorators.append(self.get_text(c, code))
        return decorators

    def extract_parameters(self, node, code):
        params = []
        for c in node.children:
            if c.type == 'formal_parameters':
                for param in c.children:
                    if param.type in ('required_parameter', 'optional_parameter'):
                        name, typ, default = None, None, None
                        for pc in param.children:
                            if pc.type in ('identifier', 'pattern', 'type_identifier'):
                                name = self.get_text(pc, code)
                            if pc.type == 'type_annotation':
                                typ = self.get_text(pc, code)
                            if pc.type == '_initializer':
                                default = self.get_text(pc, code)
                        params.append({
                            "name": name,
                            "type": typ,
                            "default": default
                        })
        return params

    def extract_all_components(self):
        return self.all_components

    def process_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        tree = self.parser.parse(bytes(code, 'utf8'))
        root_folder = os.path.dirname(file_path)
        imports = self.collect_imports_for_file(tree.root_node, code)
        components = self.walk_node(tree.root_node, code, file_path, root_folder, imports=imports)
        def is_jsonable(x):
            try:
                json.dumps(x)
                return True
            except Exception:
                return False
        self.all_components = [c for c in components if is_jsonable(c)]

    def write_to_file(self, output_path):
        serializable = []
        for comp in self.all_components:
            try:
                json.dumps(comp)
                serializable.append(comp)
            except Exception as e:
                print(f"Skipping non-serializable component: {e}")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)

    def extract_type_params(self, node, code):
        for c in node.children:
            if c.type == 'type_parameters':
                return self.get_text(c, code)
            if c.type == 'formal_type_parameters':
                return self.get_text(c, code)
        return None

    def extract_extends_implements(self, node, code):
        bases, impls = [], []
        for c in node.children:
            if c.type == 'class_heritage':
                # Look inside class_heritage for extends_clause and implements_clause
                for cc in c.children:
                    # --- Extends (inheritance) ---
                    if cc.type == 'extends_clause':
                        for base in cc.children:
                            # Tree-sitter might use 'value' as field_name for base
                            if getattr(base, "field_name", None) == "value":
                                base_name = self.get_text(base, code)
                                if base_name:
                                    bases.append(base_name)
                            elif base.type in ('identifier', 'type_identifier'):
                                base_name = self.get_text(base, code)
                                if base_name:
                                    bases.append(base_name)
                    # --- Implements (interfaces) ---
                    if cc.type == 'implements_clause':
                        for iface in cc.children:
                            # Each interface will be of type 'type'
                            if iface.type == 'type':
                                iface_name = self.get_text(iface, code)
                                if iface_name:
                                    impls.append(iface_name)
                            # Defensive: also check identifier/type_identifier
                            elif iface.type in ('identifier', 'type_identifier'):
                                iface_name = self.get_text(iface, code)
                                if iface_name:
                                    impls.append(iface_name)
        return bases, impls

    def extract_interface_extends(self, node, code):
        """Returns [parent_interface_names] for an interface_declaration node."""
        parents = []
        for c in node.children:
            if c.type == 'extends_type_clause':
                for cc in c.children:
                    if cc.type == 'type':
                        parent_name = self.get_text(cc, code)
                        if parent_name:
                            parents.append(parent_name)
        return parents
    
    def extract_expression_statement_calls(self, node, code, module_name):
        """
        Extract function/method calls of the form `object.method(args)` at the expression statement level.
        Returns a list of component dicts (to be appended to results).
        """
        results = []
        if node.type == "expression_statement":
            expr = node.children[0] if node.children else None
            if expr and expr.type == "call_expression":
                fn = expr.child_by_field_name("function")
                if fn and fn.type == "member_expression":
                    object_node = fn.child_by_field_name("object")
                    property_node = fn.child_by_field_name("property")
                    if object_node and property_node:
                        object_name = self.get_text(object_node, code)
                        property_name = self.get_text(property_node, code)
                        # Extract argument list (skipping commas)
                        arg_nodes = expr.child_by_field_name("arguments")
                        arguments = []
                        if arg_nodes:
                            for arg in arg_nodes.children:
                                if arg.type != ',':
                                    arguments.append(self.get_text(arg, code))
                        # Build a function_call component
                        results.append({
                            "kind": "function_call",
                            "module": module_name,
                            "object": object_name,
                            "method": property_name,
                            "arguments": arguments,
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                            "full_component_path": f"{module_name}::{object_name}.{property_name}"
                        })
        return results

    def extract_function_calls(self, node, code, module_name, imports, class_name=None, class_bases=None):
        """
        Recursively extract all function/method calls, handling:
        - direct calls (add(...))
        - member calls (console.log(...))
        - this.method(), super.method()
        - calls inside arguments!
        """
        calls = []

        def visit(n):
            if n.type == 'call_expression':
                fn = n.child_by_field_name('function')
                # Defensive
                if fn is None:
                    return

                # --- Handle member_expression (super.foo, this.foo, obj.foo) ---
                if fn.type == "member_expression":
                    object_node = fn.child_by_field_name("object")
                    property_node = fn.child_by_field_name("property")
                    method_name = self.get_text(property_node, code) if property_node else None

                    if object_node is not None:
                        # super.method()
                        if object_node.type == "super":
                            if class_bases and len(class_bases) > 0:
                                base_class = class_bases[0]
                                callee_id = f"{module_name}::{base_class}::{method_name}"
                            else:
                                callee_id = f"{module_name}::(super_class)::" + (method_name or "")
                            calls.append({
                                "name": f"super.{method_name}",
                                "base_name": method_name,
                                "resolved_callee": callee_id
                            })
                        # this.method()
                        elif object_node.type == "this":
                            if class_name:
                                callee_id = f"{module_name}::{class_name}::{method_name}"
                            else:
                                callee_id = f"{module_name}::(this_class)::" + (method_name or "")
                            calls.append({
                                "name": f"this.{method_name}",
                                "base_name": method_name,
                                "resolved_callee": callee_id
                            })
                        # obj.method() (could be console.log, etc)
                        elif object_node.type == "identifier":
                            obj_name = self.get_text(object_node, code)
                            callee_id = f"{module_name}::{obj_name}.{method_name}"
                            calls.append({
                                "name": f"{obj_name}.{method_name}",
                                "base_name": method_name,
                                "resolved_callee": callee_id
                            })
                    # else: fallthrough for weird AST, do nothing

                # --- Handle direct identifier calls (add(), square(), etc) ---
                elif fn.type == "identifier":
                    callee_text = self.get_text(fn, code)
                    base_name = callee_text
                    if base_name in imports:
                        source_file = imports[base_name]
                        if not source_file.endswith('.ts'):
                            source_file = source_file + '.ts'
                        source_file_name = os.path.basename(source_file)
                        callee_id = f"{source_file_name}::{base_name}"
                    else:
                        callee_id = f"{module_name}::{base_name}"
                    calls.append({
                        "name": callee_text,
                        "base_name": base_name,
                        "resolved_callee": callee_id
                    })

                # --- Recursive: Check for call expressions inside arguments ---
                args = n.child_by_field_name('arguments')
                if args:
                    for arg in args.children:
                        visit(arg)

            # Always recurse
            for c in getattr(n, 'children', []):
                visit(c)
        visit(node)
        return calls

    def extract_type_dependencies(self, node, code):
        deps = set()
        def visit(n):
            if n.type in ('type_identifier', 'predefined_type', 'nested_type_identifier', 'generic_type'):
                deps.add(self.get_text(n, code))
            # Recurse for unions/intersections and parenthesized
            elif n.type in ('union_type', 'intersection_type', 'parenthesized_type'):
                for c in n.children:
                    if c.type not in {"|", "&", "(", ")"}:
                        visit(c)
            # Recurse for all other node types (safety)
            else:
                for c in n.children:
                    visit(c)
        visit(node)
        return list(deps)


    def _get_full_component_path(self, module_name, kind, name, class_name=None):
        if class_name:
            return f"{module_name}::{class_name}::{name}"
        return f"{module_name}::{name}"

    def walk_node(self, node, code, file_path, root_folder, context=None, imports=None):
        results = []
        rel_file = os.path.relpath(file_path, root_folder)
        module_name = rel_file.replace(os.sep, '/')

        # Extract top-level function/method calls like `rect.draw()`
        results.extend(self.extract_expression_statement_calls(node, code, module_name))

        # --- Namespace/Module Extraction ---
        if node.type in ('internal_module', 'module'):
            ns_name = self.extract_ident(node, code)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            full_path = self._get_full_component_path(module_name, "namespace", ns_name)
            results.append({
                "kind": "namespace",
                "module": module_name,
                "name": ns_name,
                "start_line": start_line,
                "end_line": end_line,
                "full_component_path": full_path
            })

        # --- Variable Extraction ---
        if node.type == 'lexical_declaration':
            for child in node.children:
                if child.type == 'variable_declarator':
                    name = None
                    type_sig = None
                    value = None
                    calls = []

                    for subchild in child.children:
                        if subchild.type == 'identifier':
                            name = self.get_text(subchild, code)
                        elif subchild.type == 'type_annotation':
                            type_sig = self.get_text(subchild, code)
                        elif subchild.type == 'call_expression':
                            value = self.get_text(subchild, code)
                            fn = subchild.child_by_field_name('function')
                            if fn:
                                fn_text = self.get_text(fn, code)
                                if '.' in fn_text:
                                    mod_part, base_name = fn_text.rsplit('.', 1)
                                    calls.append({"name": fn_text, "base_name": base_name, "module_context": mod_part})
                                else:
                                    calls.append({"name": fn_text, "base_name": fn_text, "module_context": None})
                        elif subchild.type == 'conditional_expression':
                            value = self.get_text(subchild, code)
                        elif subchild.type in ('string', 'number', 'true', 'false', 'null', 'undefined'):
                            value = self.get_text(subchild, code)
                        elif subchild.type == 'new_expression':
                            value = self.get_text(subchild, code)
                            ctor = subchild.child_by_field_name('constructor')
                            arguments = []
                            for arg in subchild.children:
                                if arg.type == 'arguments':
                                    for arg_node in arg.children:
                                        if arg_node.type != ',':
                                            arguments.append(self.get_text(arg_node, code))
                            if ctor:
                                ctor_text = self.get_text(ctor, code)
                                calls.append({
                                    "kind": "constructor_call",
                                    "class_name": ctor_text,
                                    "arguments": arguments,
                                    "name": f"new {ctor_text}",
                                    "base_name": ctor_text
                                })
                        else:
                            def find_calls_in_expression(expr_node):
                                if expr_node.type == 'call_expression':
                                    nonlocal value
                                    if not value:
                                        value = self.get_text(expr_node, code)
                                    fn = expr_node.child_by_field_name('function')
                                    if fn:
                                        fn_text = self.get_text(fn, code)
                                        if '.' in fn_text:
                                            mod_part, base_name = fn_text.rsplit('.', 1)
                                            calls.append({"name": fn_text, "base_name": base_name, "module_context": mod_part})
                                        else:
                                            calls.append({"name": fn_text, "base_name": fn_text, "module_context": None})
                                for grandchild in expr_node.children:
                                    find_calls_in_expression(grandchild)

                            if not value:
                                value = self.get_text(subchild, code)
                            find_calls_in_expression(subchild)

                    if name:
                        start_line = child.start_point[0] + 1
                        end_line = child.end_point[0] + 1
                        full_path = self._get_full_component_path(module_name, "variable", name)
                        results.append({
                            "kind": "variable",
                            "module": module_name,
                            "name": name,
                            "type_signature": type_sig,
                            "value": value,
                            "function_calls": calls,
                            "start_line": start_line,
                            "end_line": end_line,
                            "full_component_path": full_path
                        })
            return results

        # --- Function Extraction ---
        if node.type in ('function_declaration', 'function_signature'):
            fn_name = self.extract_ident(node, code)
            type_sig = self.extract_type_annotation(node, code)
            type_params = self.extract_type_params(node, code)
            type_param_constraints = self.extract_type_param_constraints(node, code) # Added
            decorators = self.extract_decorators(node, code)
            params = self.extract_parameters(node, code)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            # Robustly extract the body
            body = None
            for c in node.children:
                if "block" in c.type:
                    body = c
                    break
            if body is not None:
                function_calls = self.extract_function_calls(body, code, module_name, imports)
            else:
                function_calls = []
            type_deps = self.extract_type_dependencies(node, code)
            full_path = self._get_full_component_path(module_name, "function", fn_name)
            results.append({
                "kind": "function",
                "module": module_name,
                "name": fn_name,
                "type_signature": type_sig,
                "type_parameters": type_params,
                "type_param_constraints": type_param_constraints, # Added
                "parameters": params,
                "decorators": decorators,
                "start_line": start_line,
                "end_line": end_line,
                "function_calls": function_calls,  # <--- KEY FIELD
                "type_dependencies": type_deps,
                "parent": context.get("parent") if context else None,
                "full_component_path": full_path
            })

        # --- Class Extraction ---
        if node.type in ('class_declaration', 'class', 'abstract_class_declaration'):
            class_name = self.extract_ident(node, code)
            bases, impls = self.extract_extends_implements(node, code)
            type_params = self.extract_type_params(node, code)
            type_param_constraints = self.extract_type_param_constraints(node, code) # Added
            decorators = self.extract_decorators(node, code)
            index_signatures = self.extract_index_signatures(node, code) # Added
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            full_path = self._get_full_component_path(module_name, "class", class_name)

            results.append({
                "kind": "class",
                "module": module_name,
                "name": class_name,
                "type_parameters": type_params,
                "type_param_constraints": type_param_constraints, # Added
                "decorators": decorators,
                "start_line": start_line,
                "end_line": end_line,
                "bases": bases,
                "implements": impls,
                "index_signatures": index_signatures, # Added
                "full_component_path": full_path
            })
            for c in node.children:
                if c.type == 'class_body':
                    prev_decorators = []
                    for m in c.children:
                        if m.type == 'decorator':
                            prev_decorators.append(self.get_text(m, code))
                        elif m.type == 'method_definition':
                            method_name = None
                            for child in m.children:
                                if child.type in ('property_identifier', 'identifier', 'type_identifier'):
                                    method_name = self.get_text(child, code)
                                    break
                            type_sig = self.extract_type_annotation(m, code)

                            method_body = None
                            for child in m.children:
                                if child.type in ("statement_block", "body", "block"):
                                    method_body = child
                                    break
                            if method_body is not None:
                                m_calls = self.extract_function_calls(
                                    method_body, code, module_name, imports, class_name=class_name, class_bases=bases
                                )
                            else:
                                m_calls = []

                            m_type_params = self.extract_type_params(m, code)
                            m_params = self.extract_parameters(m, code)
                            m_decorators = prev_decorators  # Attach grouped decorators
                            prev_decorators = []  # Reset after use
                            m_start = m.start_point[0] + 1
                            m_end = m.end_point[0] + 1
                            m_type_deps = self.extract_type_dependencies(m, code)
                            m_full_path = self._get_full_component_path(module_name, "method", method_name, class_name)

                            # Modifiers and Getters/Setters
                            m_mods = self.extract_modifiers(m)
                            is_getter = any(child.type == 'get' for child in m.children)
                            is_setter = any(child.type == 'set' for child in m.children)
                            
                            # Constructor check
                            kind = "constructor" if method_name == "constructor" else "method"

                            results.append({
                                "kind": kind, # Changed from "method"
                                "module": module_name,
                                "name": method_name,
                                "class": class_name,
                                "type_signature": type_sig,
                                "type_parameters": m_type_params,
                                "parameters": m_params,
                                "decorators": m_decorators,
                                "start_line": m_start,
                                "end_line": m_end,
                                "function_calls": m_calls,
                                "type_dependencies": m_type_deps,
                                "parent": class_name,
                                "full_component_path": m_full_path,
                                "static": m_mods["static"],       # Added
                                "abstract": m_mods["abstract"],   # Added
                                "readonly": m_mods["readonly"],   # Added
                                "override": m_mods["override"],   # Added
                                "getter": is_getter,              # Added
                                "setter": is_setter,              # Added
                            })
                        elif m.type == 'public_field_definition':
                            field_name = None
                            for child in m.children:
                                if child.type in ('property_identifier', 'identifier', 'type_identifier'):
                                    field_name = self.get_text(child, code)
                                    break
                            type_sig = self.extract_type_annotation(m, code)
                            m_decorators = prev_decorators  # Attach grouped decorators
                            prev_decorators = []  # Reset after use
                            m_start = m.start_point[0] + 1
                            m_end = m.end_point[0] + 1
                            f_full_path = self._get_full_component_path(module_name, "field", field_name, class_name)
                            
                            # Modifiers
                            m_mods = self.extract_modifiers(m)

                            results.append({
                                "kind": "field",
                                "module": module_name,
                                "name": field_name,
                                "class": class_name,
                                "type_signature": type_sig,
                                "decorators": m_decorators,
                                "start_line": m_start,
                                "end_line": m_end,
                                "parent": class_name,
                                "full_component_path": f_full_path,
                                "static": m_mods["static"],       # Added
                                "abstract": m_mods["abstract"],   # Added
                                "readonly": m_mods["readonly"],   # Added
                                "override": m_mods["override"],   # Added
                            })

        # --- Interface Extraction ---
        if node.type == 'interface_declaration':
            interface_name = self.extract_ident(node, code)
            type_params = self.extract_type_params(node, code)
            type_param_constraints = self.extract_type_param_constraints(node, code) # Added
            parents = self.extract_interface_extends(node, code)
            index_signatures = self.extract_index_signatures(node, code) # Added
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            full_path = self._get_full_component_path(module_name, "interface", interface_name)
            # --- Extract type dependencies for all properties ---
            type_deps = []
            for c in node.children:
                if c.type == "interface_body":
                    for member in c.children:
                        if member.type == "property_signature":
                            # The type of the property is usually in a type_annotation child
                            for prop_child in member.children:
                                if prop_child.type == "type_annotation":
                                    for type_ann_child in prop_child.children:
                                        # Could be type_identifier, generic_type, literal_type, etc.
                                        if type_ann_child.type in ("type_identifier", "predefined_type", "literal_type"):
                                            type_deps.append(self.get_text(type_ann_child, code))
                                        elif type_ann_child.type == "generic_type":
                                            type_deps += self.extract_generic_type_dependencies(type_ann_child, code)
                                        elif type_ann_child.type == "lookup_type":
                                            type_deps += self.extract_lookup_type_dependencies(type_ann_child, code)
                                        elif type_ann_child.type == "conditional_type":
                                            type_deps += self.extract_conditional_type_dependencies(type_ann_child, code)
                                        # you can add more here as needed
            # Remove duplicates
            type_deps = list(set(type_deps))
            results.append({
                "kind": "interface",
                "module": module_name,
                "name": interface_name,
                "type_parameters": type_params,
                "type_param_constraints": type_param_constraints, # Added
                "extends": parents,
                "index_signatures": index_signatures, # Added
                "type_dependencies": type_deps,
                "start_line": start_line,
                "end_line": end_line,
                "full_component_path": full_path
            })

        # --- Type Alias Extraction ---
        if node.type == 'type_alias_declaration':
            type_name = self.extract_ident(node, code)
            type_params = self.extract_type_params(node, code)
            type_param_constraints = self.extract_type_param_constraints(node, code) # Added
            type_deps = self.extract_type_dependencies(node, code)
            value_node = None
            for c in node.children:
                if c.type in ("type", "object_type", "generic_type", "union_type", "lookup_type", "conditional_type"):
                    value_node = c
                    break
                # also support multi-line definitions

            # Add dependencies for advanced type features
            if value_node:
                if value_node.type == "generic_type":
                    type_deps += self.extract_generic_type_dependencies(value_node, code)
                elif value_node.type == "lookup_type":
                    type_deps += self.extract_lookup_type_dependencies(value_node, code)
                elif value_node.type == "conditional_type":
                    type_deps += self.extract_conditional_type_dependencies(value_node, code)
                elif value_node.type == "object_type":
                    # Check for mapped type inside index_signature/mapped_type_clause
                    for child in value_node.children:
                        if child.type == "index_signature":
                            for grandchild in child.children:
                                if grandchild.type == "mapped_type_clause":
                                    type_deps += self.extract_mapped_type_dependencies(grandchild, code)
                                if grandchild.type == "type_annotation":
                                    # e.g. T[P]
                                    for ggc in grandchild.children:
                                        if ggc.type == "lookup_type":
                                            type_deps += self.extract_lookup_type_dependencies(ggc, code)
                                if grandchild.type == "opting_type_annotation":
                                    for ggc in grandchild.children:
                                        if ggc.type == "lookup_type":
                                            type_deps += self.extract_lookup_type_dependencies(ggc, code)
                elif value_node.type == "union_type":
                    # Union of multiple types/literals
                    for child in value_node.children:
                        if child.type in ("type_identifier", "literal_type"):
                            type_deps.append(self.get_text(child, code))
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            full_path = self._get_full_component_path(module_name, "type_alias", type_name)
            literal_types = self.extract_literal_types(node, code, module_name)
            literal_type_ids = [lit["id"] for lit in literal_types]
            results.append({
                "kind": "type_alias",
                "module": module_name,
                "name": type_name,
                "type_parameters": type_params,
                "type_param_constraints": type_param_constraints, # Added
                "type_dependencies": list(set(type_deps)), 
                "literal_type_dependencies": [lit["value"] for lit in literal_types], # Use literal_types to get just the values
                "start_line": start_line,
                "end_line": end_line,
                "full_component_path": full_path
            })
            
            for lit in literal_types:
                results.append(lit)

        # --- Enum Extraction ---
        if node.type == 'enum_declaration':
            enum_name = self.extract_ident(node, code)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            full_path = self._get_full_component_path(module_name, "enum", enum_name)
            results.append({
                "kind": "enum",
                "module": module_name,
                "name": enum_name,
                "start_line": start_line,
                "end_line": end_line,
                "full_component_path": full_path,
                "members": self.extract_enum_members(node, code), # Added
            })

        # --- Import/Export Extraction ---
        if node.type == 'import_statement':
            results.append({
                "kind": "import",
                "module": module_name,
                "statement": self.get_text(node, code),
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })

        if node.type == 'export_statement':
            results.append({
                "kind": "export",
                "module": module_name,
                "statement": self.get_text(node, code),
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })

        # --- Recurse for all children ---
        for c in node.children:
            results.extend(self.walk_node(c, code, file_path, root_folder, context=context, imports=imports))
        return results

    def extract_from_file(self, filepath, root_folder):
        code, tree = self.parse_file(filepath)
        root_node = tree.root_node
        return self.walk_node(root_node, code, filepath, root_folder)

    def extract_from_folder(self, folder):
        raw_components = []
        abs_folder = os.path.abspath(folder)
        for root, _, files in os.walk(abs_folder):
            for f in files:
                if f.endswith('.ts'):
                    raw_components.extend(self.extract_from_file(os.path.join(root, f), abs_folder))
        return raw_components
    def extract_literal_types(self, node, code, module_name):
        """Recursively find all literal_type nodes under the given node."""
        literals = []
        def visit(n):
            if n.type == 'literal_type':
                # This will get the source text, e.g. '"north"', '404', 'true'
                literal_value = self.get_text(n, code)
                # Compose a unique name/id for this literal
                literal_id = f"{module_name}::{literal_value}"
                literals.append({
                    "kind": "literal_type",
                    "name": literal_value,           # for consistency
                    "value": literal_value,
                    "module": module_name,
                    "id": literal_id,
                    "start_line": n.start_point[0] + 1,
                    "end_line": n.end_point[0] + 1,
                    "full_component_path": literal_id
                })
            for c in n.children:
                visit(c)
        visit(node)
        return literals