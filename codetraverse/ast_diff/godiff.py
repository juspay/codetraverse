import json
from tree_sitter import Language, Parser, Node
import tree_sitter_go
from Detailedchanges import DetailedChanges
from basefilediff import BaseFileDiff
class GoFileDiff(BaseFileDiff):
    """Analyzes and compares two Go ASTs for semantic differences."""
    def __init__(self, module_name=""):
        self.changes = DetailedChanges(module_name)

    def get_decl_name(self, node: Node) -> str:
        """Finds the name of a Go declaration."""
        if node.type == 'method_declaration':
            receiver = node.child_by_field_name('receiver')
            name = node.child_by_field_name('name')
            if receiver and name:
                return f"{receiver.text.decode('utf8')} {name.text.decode('utf8')}"
        
        name_node = node.child_by_field_name('name')
        if name_node:
            return name_node.text.decode('utf8')
        return None

    def extract_components(self, root: Node):
        """Extracts all top-level declarations from a Go AST."""
        functions, types, variables, constants, imports = {}, {}, {}, {}, {}
        
        top_level_types = [
            "function_declaration", "method_declaration", "type_declaration",
            "var_declaration", "const_declaration", "import_declaration",
        ]
        
        if root.type == 'source_file':
            for child in root.children:
                if child.type in top_level_types:
                    if child.type == 'import_declaration':
                        # CORRECTED LOGIC: Search for all import_spec nodes inside
                        # an import_declaration to handle both single and block imports.
                        queue = list(child.children)
                        while queue:
                            current = queue.pop(0)
                            if current.type == 'import_spec':
                                path_node = current.child_by_field_name('path')
                                if path_node:
                                    name = path_node.text.decode('utf8')
                                    imports[name] = (current, current.text.decode('utf8'), current.start_point, current.end_point)
                            else:
                                queue.extend(current.children)
                    elif child.type == 'type_declaration':
                        for type_spec in child.children:
                            if type_spec.type == 'type_spec':
                                name = self.get_decl_name(type_spec)
                                if name: types[name] = (type_spec, type_spec.text.decode('utf8'), type_spec.start_point, type_spec.end_point)
                    elif child.type == 'var_declaration':
                        for var_spec in child.children:
                            if var_spec.type == 'var_spec':
                                for name_node in var_spec.children_by_field_name('name'):
                                    name = name_node.text.decode('utf8')
                                    variables[name] = (var_spec, var_spec.text.decode('utf8'), var_spec.start_point, var_spec.end_point)
                    elif child.type == 'const_declaration':
                         for const_spec in child.children:
                            if const_spec.type == 'const_spec':
                                for name_node in const_spec.children_by_field_name('name'):
                                    name = name_node.text.decode('utf8')
                                    constants[name] = (const_spec, const_spec.text.decode('utf8'), const_spec.start_point, const_spec.end_point)
                    else:
                        name = self.get_decl_name(child)
                        if name:
                            functions[name] = (child, child.text.decode('utf8'), child.start_point, child.end_point)

        return functions, types, variables, constants, imports

    def diff_components(self, before_map: dict, after_map: dict):
        """Compares two dictionaries of components and returns the diff."""
        before_names, after_names = set(before_map.keys()), set(after_map.keys())
        added_names, deleted_names, common_names = after_names - before_names, before_names - after_names, before_names & after_names
        
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
        """The main method to compare two Go files."""
        old_funcs, old_types, old_vars, old_consts, old_imports = self.extract_components(old_file_ast.root_node)
        new_funcs, new_types, new_vars, new_consts, new_imports = self.extract_components(new_file_ast.root_node)

        # Define what we're comparing
        category_map = {
            "Functions": (old_funcs, new_funcs),
            "Types": (old_types, new_types),
            "Vars": (old_vars, new_vars),
            "Consts": (old_consts, new_consts),
            "Imports": (old_imports, new_imports),
        }

        # Run diff and record changes
        for category, (old_map, new_map) in category_map.items():
            diff = self.diff_components(old_map, new_map)
            for change_type in ["added", "deleted", "modified"]:
                for item in diff[change_type]:
                    self.changes.add_change(category.lower(), change_type, item)

        return self.changes
    
    def process_single_file(self, file_ast: Node, mode="deleted") -> DetailedChanges:
        """Processes a single file that was either entirely added or deleted."""
        funcs, types, variables, constants, imports = self.extract_components(file_ast.root_node)

        category_map = {
            "functions": funcs,
            "types": types,
            "vars": variables,
            "consts": constants,
            "imports": imports,
        }

        for category, component_map in category_map.items():
            for name, data_tuple in component_map.items():
                # data_tuple is (node, text, start_point, end_point)
                item = (name, data_tuple[1], {"start": data_tuple[2], "end": data_tuple[3]})
                self.changes.add_change(category, mode, item)
        
        return self.changes

