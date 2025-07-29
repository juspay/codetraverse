from tree_sitter import Node
from .Detailedchanges import DetailedChanges
from .basefilediff import BaseFileDiff

class PureScriptFileDiff(BaseFileDiff):
    """Analyzes and compares two PureScript ASTs for semantic differences."""

    def __init__(self, module_name=""):
        self.changes = DetailedChanges(module_name)

    def get_decl_name(self, node: Node) -> str:
        """Finds the name of a PureScript declaration."""
        # Case 1: Standard declarations with a 'name' field
        name_node = node.child_by_field_name('name')
        if name_node:
            return name_node.text.decode('utf8')

        # Case 2: Function declarations (name is the first identifier)
        if node.type == 'function':
            if node.child_count > 0 and node.children[0].type == 'identifier':
                return node.children[0].text.decode('utf8')

        # Case 3: Type aliases (e.g., `type String = ...`)
        if node.type == 'type_alias_declaration':
            # The structure is typically `type_alias_declaration -> type_variable_binding -> type_identifier`
            tvb_node = next((c for c in node.children if c.type == 'type_variable_binding'), None)
            if tvb_node:
                name_node = next((c for c in tvb_node.children if c.type == 'type_identifier'), None)
                if name_node:
                    return name_node.text.decode('utf8')

        # Case 4: Foreign imports (e.g., `foreign import foo :: Int`)
        if node.type == 'foreign_import':
            name_node = next((c for c in node.children if c.type == 'identifier'), None)
            if name_node:
                return name_node.text.decode('utf8')

        # Case 5: Class instances (e.g., `instance showInt :: Show Int`)
        if node.type == 'class_instance':
            # Create a composite name like "Show Int"
            instance_name_node = node.child_by_field_name('instance_name')
            if instance_name_node:
                # The instance name itself can be complex, so we take its full text
                return instance_name_node.text.decode('utf8').strip()

        return None

    def extract_components(self, root: Node):
        """Extracts all declarations from a PureScript AST using recursive traversal."""
        items = {
            "functions": {}, "classes": {}, "data_declarations": {},
            "newtypes": {}, "type_aliases": {}, "foreign_imports": {},
            "instances": {},
        }

        node_type_map = {
            "function": items["functions"],
            "class_declaration": items["classes"],
            "data_declaration": items["data_declarations"],
            "newtype": items["newtypes"],
            "type_alias_declaration": items["type_aliases"],
            "foreign_import": items["foreign_imports"],
            "class_instance": items["instances"],
        }

        queue = [root]
        while queue:
            current_node = queue.pop(0)
            if current_node.type in node_type_map:
                name = self.get_decl_name(current_node)
                if name:
                    target_dict = node_type_map[current_node.type]
                    target_dict[name] = (current_node, current_node.text.decode('utf8'), current_node.start_point, current_node.end_point)
            
            # Continue traversal
            for child in current_node.children:
                queue.append(child)

        return items

    def deep_equal(self, nodeA: Node, nodeB: Node) -> bool:
        """Recursively checks if two AST nodes are structurally identical."""
        if (nodeA is None) != (nodeB is None):
            return False
        if nodeA is None and nodeB is None:
            return True
        if nodeA.type != nodeB.type:
            return False
        
        # For leaf nodes, compare text content
        if not nodeA.children:
            return nodeA.text == nodeB.text

        if len(nodeA.children) != len(nodeB.children):
            return False

        for childA, childB in zip(nodeA.children, nodeB.children):
            if not self.deep_equal(childA, childB):
                return False

        return True

    def diff_components(self, before_map: dict, after_map: dict):
        """Compares two dictionaries of components using deep equality and returns the diff."""
        before_names = set(before_map.keys())
        after_names = set(after_map.keys())
        
        added_names = after_names - before_names
        deleted_names = before_names - after_names
        common_names = before_names & after_names
        
        added = [(n, after_map[n][1], {"start": after_map[n][2], "end": after_map[n][3]}) for n in sorted(added_names)]
        deleted = [(n, before_map[n][1], {"start": before_map[n][2], "end": before_map[n][3]}) for n in sorted(deleted_names)]
        
        modified = []
        for name in sorted(common_names):
            old_ast, old_body, old_start, old_end = before_map[name]
            new_ast, new_body, new_start, new_end = after_map[name]
            
            # Use deep_equal for robust comparison
            if not self.deep_equal(old_ast, new_ast):
                 modified.append((name, old_body, new_body, {"old_start": old_start, "old_end": old_end, "new_start": new_start, "new_end": new_end}))
        
        return {"added": added, "deleted": deleted, "modified": modified}

    def compare_two_files(self, old_file_ast: Node, new_file_ast: Node) -> DetailedChanges:
        """The main method to compare two PureScript files."""
        old_items = self.extract_components(old_file_ast.root_node)
        new_items = self.extract_components(new_file_ast.root_node)

        # Iterate over all component categories (functions, classes, types, etc.)
        all_categories = set(old_items.keys()) | set(new_items.keys())

        for category in all_categories:
            old_map = old_items.get(category, {})
            new_map = new_items.get(category, {})
            
            diff = self.diff_components(old_map, new_map)
            
            for change_type in ["added", "deleted", "modified"]:
                for data in diff[change_type]:
                    self.changes.add_change(category, change_type, data)

        return self.changes
    
    def process_single_file(self, file_ast: Node, mode="deleted") -> DetailedChanges:
        """Processes a single file that was either entirely added or deleted."""
        items = self.extract_components(file_ast.root_node)

        for category, component_map in items.items():
            for name, data_tuple in component_map.items():
                item = (name, data_tuple[1], {"start": data_tuple[2], "end": data_tuple[3]})
                self.changes.add_change(category, mode, item)
        
        return self.changes