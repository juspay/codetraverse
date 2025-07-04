import json
from tree_sitter import Language, Parser, Node
import tree_sitter_go

class DetailedChanges:
    """A data class to hold the results of a diff operation for Go."""
    def __init__(self, module_name):
        self.moduleName = module_name
        # ... (other component lists remain the same) ...
        self.addedFunctions = []
        self.modifiedFunctions = []
        self.deletedFunctions = []

        self.addedTypes = []
        self.modifiedTypes = []
        self.deletedTypes = []

        self.addedVars = []
        self.modifiedVars = []
        self.deletedVars = []

        self.addedConsts = []
        self.modifiedConsts = []
        self.deletedConsts = []
        
        # Added for imports
        self.addedImports = []
        self.modifiedImports = []
        self.deletedImports = []

    def to_dict(self):
        """Converts the object to a dictionary for JSON serialization."""
        return {
            "moduleName": self.moduleName,
            "addedFunctions": self.addedFunctions, "modifiedFunctions": self.modifiedFunctions, "deletedFunctions": self.deletedFunctions,
            "addedTypes": self.addedTypes, "modifiedTypes": self.modifiedTypes, "deletedTypes": self.deletedTypes,
            "addedVars": self.addedVars, "modifiedVars": self.modifiedVars, "deletedVars": self.deletedVars,
            "addedConsts": self.addedConsts, "modifiedConsts": self.modifiedConsts, "deletedConsts": self.deletedConsts,
            "addedImports": self.addedImports, "modifiedImports": self.modifiedImports, "deletedImports": self.deletedImports,
        }

    def __str__(self):
        parts = []
        # ... (other summary parts remain the same) ...
        if self.addedImports or self.modifiedImports or self.deletedImports:
            parts.append(f"Imports: +{len(self.addedImports)} ~{len(self.modifiedImports)} -{len(self.deletedImports)}")
        
        return f"Module: {self.moduleName}\n" + "\n".join(parts)

class GoFileDiff:
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
            _, old_body, _, _ = before_map[name]
            _, new_body, old_start, old_end = after_map[name]
            if old_body.strip() != new_body.strip():
                 modified.append((name, old_body, new_body, {"old_start": old_start, "old_end": old_end}))
        return {"added": added, "deleted": deleted, "modified": modified}

    def compare_two_files(self, old_file_ast: Node, new_file_ast: Node) -> DetailedChanges:
        """The main method to compare two Go files."""
        old_funcs, old_types, old_vars, old_consts, old_imports = self.extract_components(old_file_ast.root_node)
        new_funcs, new_types, new_vars, new_consts, new_imports = self.extract_components(new_file_ast.root_node)

        funcs_diff = self.diff_components(old_funcs, new_funcs)
        self.changes.addedFunctions, self.changes.deletedFunctions, self.changes.modifiedFunctions = funcs_diff["added"], funcs_diff["deleted"], funcs_diff["modified"]
        
        types_diff = self.diff_components(old_types, new_types)
        self.changes.addedTypes, self.changes.deletedTypes, self.changes.modifiedDataTypes = types_diff["added"], types_diff["deleted"], types_diff["modified"]

        vars_diff = self.diff_components(old_vars, new_vars)
        self.changes.addedVars, self.changes.deletedVars, self.changes.modifiedVars = vars_diff["added"], vars_diff["deleted"], vars_diff["modified"]

        consts_diff = self.diff_components(old_consts, new_consts)
        self.changes.addedConsts, self.changes.deletedConsts, self.changes.modifiedConsts = consts_diff["added"], consts_diff["deleted"], consts_diff["modified"]
        
        imports_diff = self.diff_components(old_imports, new_imports)
        self.changes.addedImports, self.changes.deletedImports, self.changes.modifiedImports = imports_diff["added"], imports_diff["deleted"], imports_diff["modified"]
        
        return self.changes

# Main execution block
if __name__ == "__main__":
    GO_LANGUAGE = Language(tree_sitter_go.language())
    parser = Parser(GO_LANGUAGE)

    # --- BEFORE ---
    file1_content = """
ppackage main

import "fmt"

func main() {
    fmt.Println("Hello")
}
"""

    # --- AFTER ---
    # Added "strings" import, removed "fmt"
    file2_content = """
package main

import f "fmt"

func main() {
    f.Println("Hello")
}
"""
    ast1 = parser.parse(bytes(file1_content, "utf8"))
    ast2 = parser.parse(bytes(file2_content, "utf8"))

    differ = GoFileDiff("main.go")
    changes = differ.compare_two_files(ast1, ast2)

    print("--- FINAL SUMMARY ---")
    print(changes)
    
    print("\n--- FINAL JSON OUTPUT ---")
    print(json.dumps(changes.to_dict(), indent=2))