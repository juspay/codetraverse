import json
from tree_sitter import Language, Parser, Node
import tree_sitter_haskell

class DetailedChanges:
    """A data class to hold the results of a diff operation."""
    def __init__(self, module_name):
        self.moduleName = module_name
        self.addedFunctions = []
        self.modifiedFunctions = []
        self.deletedFunctions = []

        self.addedDataTypes = []
        self.modifiedDataTypes = []
        self.deletedDataTypes = []
        
        self.addedTypeClasses = []
        self.modifiedTypeClasses = []
        self.deletedTypeClasses = []

        self.addedInstances = []
        self.modifiedInstances = []
        self.deletedInstances = []

    def to_dict(self):
        """Converts the object to a dictionary for JSON serialization."""
        return {
            "moduleName": self.moduleName,
            "addedFunctions": self.addedFunctions,
            "modifiedFunctions": self.modifiedFunctions,
            "deletedFunctions": self.deletedFunctions,
            "addedDataTypes": self.addedDataTypes,
            "modifiedDataTypes": self.modifiedDataTypes,
            "deletedDataTypes": self.deletedDataTypes,
            "addedTypeClasses": self.addedTypeClasses,
            "modifiedTypeClasses": self.modifiedTypeClasses,
            "deletedTypeClasses": self.deletedTypeClasses,
            "addedInstances": self.addedInstances,
            "modifiedInstances": self.modifiedInstances,
            "deletedInstances": self.deletedInstances,
        }

    def __str__(self):
        # Abridged string representation for cleaner printing
        parts = []
        if self.addedFunctions or self.modifiedFunctions or self.deletedFunctions:
            parts.append(f"Functions: +{len(self.addedFunctions)} ~{len(self.modifiedFunctions)} -{len(self.deletedFunctions)}")
        if self.addedDataTypes or self.modifiedDataTypes or self.deletedDataTypes:
            parts.append(f"DataTypes: +{len(self.addedDataTypes)} ~{len(self.modifiedDataTypes)} -{len(self.deletedDataTypes)}")
        if self.addedTypeClasses or self.modifiedTypeClasses or self.deletedTypeClasses:
            parts.append(f"TypeClasses: +{len(self.addedTypeClasses)} ~{len(self.modifiedTypeClasses)} -{len(self.deletedTypeClasses)}")
        if self.addedInstances or self.modifiedInstances or self.deletedInstances:
            parts.append(f"Instances: +{len(self.addedInstances)} ~{len(self.modifiedInstances)} -{len(self.deletedInstances)}")
        
        return f"Module: {self.moduleName}\n" + "\n".join(parts)


class HaskellFileDiff:
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
        print(declarations)
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

        funcs_diff = self.diff_components(old_funcs, new_funcs)
        self.changes.addedFunctions, self.changes.deletedFunctions, self.changes.modifiedFunctions = funcs_diff["added"], funcs_diff["deleted"], funcs_diff["modified"]
        
        data_diff = self.diff_components(old_data, new_data)
        self.changes.addedDataTypes, self.changes.deletedDataTypes, self.changes.modifiedDataTypes = data_diff["added"], data_diff["deleted"], data_diff["modified"]

        class_diff = self.diff_components(old_classes, new_classes)
        self.changes.addedTypeClasses, self.changes.deletedTypeClasses, self.changes.modifiedTypeClasses = class_diff["added"], class_diff["deleted"], class_diff["modified"]

        # Diff instances
        inst_diff = self.diff_components(old_instances, new_instances)
        self.changes.addedInstances, self.changes.deletedInstances, self.changes.modifiedInstances = inst_diff["added"], inst_diff["deleted"], inst_diff["modified"]
        return self.changes
