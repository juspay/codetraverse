import json
from tree_sitter import Language, Parser, Node
import tree_sitter_python
from .Detailedchanges import DetailedChanges
from .basefilediff import BaseFileDiff

class PythonFileDiff(BaseFileDiff):
    """Analyzes and compares two Python ASTs for semantic differences."""
    def __init__(self, module_name=""):
        self.changes = DetailedChanges(module_name)

    def get_decl_name(self, node: Node) -> str:
        """Finds the name of a Python declaration."""
        # For decorated definitions, recurse into the actual definition
        if node.type == 'decorated_definition':
            definition = node.child_by_field_name('definition')
            if definition:
                return self.get_decl_name(definition)

        # For functions and classes, the name is in the 'name' field
        name_node = node.child_by_field_name('name')
        if name_node:
            return name_node.text.decode('utf8')
        
        # For assignments, get the variable name
        if node.type == 'assignment':
            left_node = node.child_by_field_name('left')
            if left_node and left_node.type == 'identifier':
                return left_node.text.decode('utf8')

        return None

    def extract_components(self, root: Node):
        """Extracts all top-level declarations from a Python AST."""
        functions, classes, imports, variables = {}, {}, {}, {}
        
        node_type_map = {
            'function_definition': functions,
            'class_definition': classes,
        }

        for child in root.children:
            node_to_process = child
            
            # Handle decorated definitions by looking at the inner definition
            if child.type == 'decorated_definition':
                definition_node = child.child_by_field_name('definition')
                if definition_node:
                    node_to_process = definition_node
            
            node_type = node_to_process.type

            if node_type in node_type_map:
                name = self.get_decl_name(child) # Use original child to get name from decorator if needed
                if name:
                    target_dict = node_type_map[node_type]
                    target_dict[name] = (child, child.text.decode(errors="ignore"), child.start_point, child.end_point)
            
            elif node_type in ['import_statement', 'import_from_statement']:
                # Record the whole import line as one component
                name = child.text.decode('utf8')
                imports[name] = (child, name, child.start_point, child.end_point)

            # Capture top-level variable assignments
            elif node_type == 'expression_statement' and child.child(0).type == 'assignment':
                assignment_node = child.child(0)
                name = self.get_decl_name(assignment_node)
                if name:
                    variables[name] = (child, child.text.decode(errors="ignore"), child.start_point, child.end_point)

        return functions, classes, imports, variables

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
        """The main method to compare two Python files."""
        old_funcs, old_classes, old_imports, old_vars = self.extract_components(old_file_ast.root_node)
        new_funcs, new_classes, new_imports, new_vars = self.extract_components(new_file_ast.root_node)

        category_map = {
            "functions": (old_funcs, new_funcs),
            "classes": (old_classes, new_classes),
            "imports": (old_imports, new_imports),
            "variables": (old_vars, new_vars),
        }
        
        print("/n/n/n/n category map"  ,category_map)

        for category, (old_map, new_map) in category_map.items():
            diff = self.diff_components(old_map, new_map)
            for change_type in ["added", "deleted", "modified"]:
                for item in diff[change_type]:
                    self.changes.add_change(category, change_type, item)

        return self.changes
        
    def process_single_file(self, file_ast: Node, mode="deleted") -> DetailedChanges:
        """Processes a single file that was either entirely added or deleted."""
        funcs, classes, imports, variables = self.extract_components(file_ast.root_node)

        category_map = {
            "functions": funcs,
            "classes": classes,
            "imports": imports,
            "variables": variables,
        }

        for category, component_map in category_map.items():
            for name, data_tuple in component_map.items():
                item = (name, data_tuple[1], {"start": data_tuple[2], "end": data_tuple[3]})
                self.changes.add_change(category, mode, item)
        
        return self.changes
