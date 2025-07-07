import json
from tree_sitter import Language, Parser, Node
import tree_sitter_haskell
from Detailedchanges import DetailedChanges
from basefilediff import BaseFileDiff

class HaskellFileDiff(BaseFileDiff):
    """Analyzes and compares two Haskell ASTs for semantic differences."""
    def __init__(self, module_name=""):
        self.changes = DetailedChanges(module_name)

    def get_decl_name(self, node: Node) -> str:
        """Finds the name of a declaration. For instances, it extracts the instance head."""
        # For instances, the "name" is the instance head (e.g., "Eq (Maybe a)")
        if node.type == 'instance':
            # The instance head is typically the part between 'instance' and 'where'
            instance_head_nodes = []
            for child in node.children:
                if child.type == 'where':
                    break
                if child.type != 'instance':
                    instance_head_nodes.append(child.text.decode(errors="ignore"))
            return " ".join(instance_head_nodes).strip()

        # For other types, find the first variable or constructor
        queue = list(node.children)
        while queue:
            current = queue.pop(0)
            if current.type in ["variable", "constructor"]:
                return current.text.decode(errors="ignore")
            if current.is_named:
                queue.extend(current.children)
        return None

    def extract_components(self, root: Node):
        """Extracts all top-level Haskell declarations from an AST."""
        functions, data_types, type_classes, instances = {}, {}, {}, {}
        
        node_type_map = {
            "function": functions,
            "signature": functions,
            "data_type": data_types,
            "class": type_classes,
            "instance": instances,  # Track instances
        }
        
        declarations = []
        if root.type == 'haskell':
            declarations_node = next((c for c in root.children if c.type == 'declarations'), None)
            if declarations_node:
                declarations = declarations_node.children
        for child in declarations:
            if child.type in node_type_map:
                name = self.get_decl_name(child)
                if name:
                    target_dict = node_type_map[child.type]
                    if name not in target_dict:
                        target_dict[name] = (child, child.text.decode(errors="ignore"), child.start_point, child.end_point)
                    else:
                        _, existing_text, start, _ = target_dict[name]
                        new_text = existing_text + "\n" + child.text.decode(errors="ignore")
                        target_dict[name] = (child, new_text, start, child.end_point)
        return functions, data_types, type_classes, instances

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
            _, old_body, _, _ = before_map[name]
            _, new_body, old_start, old_end = after_map[name]
            if old_body.strip() != new_body.strip():
                 modified.append((name, old_body, new_body, {"old_start": old_start, "old_end": old_end}))
        return {"added": added, "deleted": deleted, "modified": modified}

    def compare_two_files(self, old_file_ast: Node, new_file_ast: Node) -> DetailedChanges:
        """The main method to compare two Haskell files."""
        old_funcs, old_data, old_classes, old_instances = self.extract_components(old_file_ast.root_node)
        new_funcs, new_data, new_classes, new_instances = self.extract_components(new_file_ast.root_node)

        category_map = {
            "functions": (old_funcs, new_funcs),
            "dataTypes": (old_data, new_data),
            "typeClasses": (old_classes, new_classes),
            "instances": (old_instances, new_instances),
        }

        for category, (old_map, new_map) in category_map.items():
            diff = self.diff_components(old_map, new_map)
            for change_type in ["added", "deleted", "modified"]:
                for item in diff[change_type]:
                    self.changes.add_change(category, change_type, item)

        return self.changes
    
    def process_single_file(self, file_ast: Node, mode="deleted") -> DetailedChanges:
        funcs, data, classes, instances = self.extract_components(file_ast.root_node)

        category_map = {
            "functions": funcs,
            "dataTypes": data,
            "typeClasses": classes,
            "instances": instances,
        }

        for category, component_map in category_map.items():
            for name, data_tuple in component_map.items():
                # data_tuple is (node, text, start_point, end_point)
                item = (name, data_tuple[1], {"start": data_tuple[2], "end": data_tuple[3]})
                self.changes.add_change(category, mode, item)
        
        return self.changes
    
