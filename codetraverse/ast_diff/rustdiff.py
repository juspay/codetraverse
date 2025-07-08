import json
from tree_sitter import Language, Parser, Node
import tree_sitter_rust
from .Detailedchanges import DetailedChanges
from .basefilediff import BaseFileDiff
class RustFileDiff(BaseFileDiff):
    """Analyzes and compares two Rust ASTs for semantic differences."""
    def __init__(self, module_name=""):
        self.changes = DetailedChanges(module_name)

    def get_decl_name(self, node: Node) -> str:
        """Finds the name of a Rust declaration."""
        # Handle `impl` blocks by creating a composite name
        if node.type == 'impl_item':
            trait = node.child_by_field_name('trait')
            type_node = node.child_by_field_name('type')
            if trait and type_node:
                return f"{trait.text.decode('utf8')} for {type_node.text.decode('utf8')}"
            elif type_node:
                return type_node.text.decode('utf8')
        
        # Handle `use` declarations
        if node.type == 'use_declaration':
            arg_node = node.child_by_field_name('argument')
            if arg_node:
                return arg_node.text.decode('utf8')

        # For most other declarations, the name is in a 'name' field
        name_node = node.child_by_field_name('name')
        if name_node:
            return name_node.text.decode('utf8')
        return None

    def extract_components(self, root: Node):
        """Extracts all top-level declarations from a Rust AST."""
        items = {
            "functions": {}, "structs": {}, "enums": {}, "traits": {},
            "impls": {}, "uses": {}, "consts": {},
        }
        
        node_type_map = {
            "function_item": items["functions"],
            "struct_item": items["structs"],
            "enum_item": items["enums"],
            "trait_item": items["traits"],
            "impl_item": items["impls"],
            "use_declaration": items["uses"],
            "const_item": items["consts"],
            "static_item": items["consts"], # Treat statics like consts
            "type_item": items["structs"], # Treat type aliases like structs
        }
        
        if root.type == 'source_file':
            for child in root.children:
                if child.type in node_type_map:
                    name = self.get_decl_name(child)
                    if name:
                        target_dict = node_type_map[child.type]
                        target_dict[name] = (child, child.text.decode('utf8'), child.start_point, child.end_point)

        return items

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
        """The main method to compare two Rust files."""
        old_items = self.extract_components(old_file_ast.root_node)
        new_items = self.extract_components(new_file_ast.root_node)

        for category in ["functions", "structs", "enums", "traits", "impls", "uses", "consts"]:
            diff = self.diff_components(old_items[category], new_items[category])
            for change_type in ["added", "deleted", "modified"]:
                for data in diff[change_type]:
                    self.changes.add_change(category, change_type, data)

        return self.changes
    
    def process_single_file(self, file_ast: Node, mode="deleted") -> DetailedChanges:
        """Processes a single file that was either entirely added or deleted."""
        items = self.extract_components(file_ast.root_node)

        for category, component_map in items.items():
            for name, data_tuple in component_map.items():
                # data_tuple is (node, text, start_point, end_point)
                item = (name, data_tuple[1], {"start": data_tuple[2], "end": data_tuple[3]})
                self.changes.add_change(category, mode, item)
        
        return self.changes