import json
from tree_sitter import Language, Parser, Node
import tree_sitter_typescript
from .Detailedchanges import DetailedChanges
from .basefilediff import BaseFileDiff

class TypeScriptFileDiff(BaseFileDiff):
    """Analyzes and compares two TypeScript ASTs for semantic differences."""
    def __init__(self, module_name=""):
        self.changes = DetailedChanges(module_name)

    def get_decl_name(self, node: Node) -> str:
        """Finds the name of a TypeScript declaration."""
        # Handle `export` statements by looking inside them
        if node.type == 'export_statement':
            if node.named_child_count > 0:
                declaration_node = node.named_child(node.named_child_count - 1)
                if declaration_node:
                    return self.get_decl_name(declaration_node)

        # Handle `const myFunc = () => {}` or `const myVar = 1;`
        if node.type == 'lexical_declaration':
            # A lexical declaration can have multiple declarators, like `const a = 1, b = 2;`
            # We'll just grab the name from the first one for simplicity.
            declarator_node = node.named_child(0)
            if declarator_node and declarator_node.type == 'variable_declarator':
                name_node = declarator_node.child_by_field_name('name')
                if name_node:
                    return name_node.text.decode('utf8')

        # Handle `function`, `class`, `interface`, etc.
        name_node = node.child_by_field_name('name')
        if name_node:
            return name_node.text.decode('utf8')

        return None

    def extract_components(self, root: Node):
        """Extracts all top-level declarations from a TypeScript AST, including functions inside objects."""
        functions, classes, interfaces, types, enums, constants = {}, {}, {}, {}, {}, {}
        
        node_type_map = {
            'function_declaration': functions,
            'class_declaration': classes,
            'interface_declaration': interfaces,
            'type_alias_declaration': types,
            'enum_declaration': enums,
        }
        
        declarations = root.children if root.type == 'program' else []

        for child in declarations:
            node_to_process = child
            
            # Look inside `export` statements
            if child.type == 'export_statement':
                if child.named_child_count > 0:
                    declaration_node = child.named_child(child.named_child_count - 1)
                    if declaration_node:
                        node_to_process = declaration_node
            
            node_type = node_to_process.type

            if node_type == 'lexical_declaration':
                declarator = node_to_process.named_child(0)
                if declarator and declarator.type == 'variable_declarator':
                    name = self.get_decl_name(child)
                    value_node = declarator.child_by_field_name('value')
                    
                    if name and value_node:
                        # Handle `as const` expressions by unwrapping them
                        actual_value_node = value_node
                        if actual_value_node.type == 'as_expression' and actual_value_node.child_count > 0:
                            actual_value_node = actual_value_node.child(0)

                        # Case 1: const is an arrow function
                        if actual_value_node.type == 'arrow_function':
                            data_tuple = (child, child.text.decode(errors="ignore"), child.start_point, child.end_point)
                            functions[name] = data_tuple
                        
                        # Case 2: const is an object, which might contain functions (common in .tsx)
                        elif actual_value_node.type == 'object':
                            # The object itself is a constant
                            data_tuple = (child, child.text.decode(errors="ignore"), child.start_point, child.end_point)
                            constants[name] = data_tuple
                            
                            # Now, look for functions inside the object's properties
                            for pair_node in actual_value_node.children:
                                if pair_node.type == 'pair':
                                    key_node = pair_node.child_by_field_name('key')
                                    val_node = pair_node.child_by_field_name('value')
                                    
                                    if key_node and val_node and val_node.type == 'arrow_function':
                                        inner_func_name = f"{name}.{key_node.text.decode('utf8')}"
                                        inner_data_tuple = (pair_node, pair_node.text.decode(errors="ignore"), pair_node.start_point, pair_node.end_point)
                                        functions[inner_func_name] = inner_data_tuple
                        
                        # Case 3: const is something else
                        else:
                            data_tuple = (child, child.text.decode(errors="ignore"), child.start_point, child.end_point)
                            constants[name] = data_tuple

            elif node_type in node_type_map:
                name = self.get_decl_name(child)
                if name:
                    target_dict = node_type_map[node_type]
                    target_dict[name] = (child, child.text.decode(errors="ignore"), child.start_point, child.end_point)

        return functions, classes, interfaces, types, enums, constants

    def diff_components(self, before_map: dict, after_map: dict):
        """Compares two dictionaries of components and returns the diff."""
        before_names = set(before_map.keys())
        after_names = set(after_map.keys())
        added_names = after_names - before_names
        deleted_names = before_names - after_names
        common_names = before_names & after_names
        
        added = [(n, after_map[n][1], {"start": after_map[n][2], "end": after_map[n][3]}) for n in sorted(added_names)]
        deleted = [(n, before_map[n][1], {"start": before_map[n][2], "end": before_map[n][3]}) for n in sorted(deleted_names)]
        modified = []
        for name in sorted(common_names):
            _, old_body, old_start, old_end = before_map[name]
            _, new_body, new_start, new_end = after_map[name]
            if old_body.strip() != new_body.strip():
                 modified.append((name, old_body, new_body, {"old_start": old_start, "old_end": old_end, "new_start": new_start, "new_end": new_end}))
        return {"added": added, "deleted": deleted, "modified": modified}

    def compare_two_files(self, old_file_ast: Node, new_file_ast: Node) -> DetailedChanges:
        """The main method to compare two TypeScript files."""
        old_funcs, old_classes, old_ifaces, old_types, old_enums, old_consts = self.extract_components(old_file_ast.root_node)
        new_funcs, new_classes, new_ifaces, new_types, new_enums, new_consts = self.extract_components(new_file_ast.root_node)

        # Define what we're comparing
        category_map = {
            "functions": (old_funcs, new_funcs),
            "classes": (old_classes, new_classes),
            "interfaces": (old_ifaces, new_ifaces),
            "types": (old_types, new_types),
            "enums": (old_enums, new_enums),
            "constants": (old_consts, new_consts),
        }

        # Run diff and record changes
        for category, (old_map, new_map) in category_map.items():
            diff = self.diff_components(old_map, new_map)
            for change_type in ["added", "deleted", "modified"]:
                for item in diff[change_type]:
                    self.changes.add_change(category, change_type, item)

        return self.changes
        
    def process_single_file(self, file_ast: Node, mode="deleted") -> DetailedChanges:
        """Processes a single file that was either entirely added or deleted."""
        funcs, classes, interfaces, types, enums, consts = self.extract_components(file_ast.root_node)

        category_map = {
            "functions": funcs,
            "classes": classes,
            "interfaces": interfaces,
            "types": types,
            "enums": enums,
            "constants": consts,
        }

        for category, component_map in category_map.items():
            for name, data_tuple in component_map.items():
                # data_tuple is (node, text, start_point, end_point)
                item = (name, data_tuple[1], {"start": data_tuple[2], "end": data_tuple[3]})
                self.changes.add_change(category, mode, item)
        
        return self.changes
