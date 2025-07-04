import json
from tree_sitter import Language, Parser, Node
import tree_sitter_typescript

class DetailedChanges:
    """A data class to hold the results of a diff operation for TypeScript."""
    def __init__(self, module_name):
        self.moduleName = module_name
        self.addedFunctions = []
        self.modifiedFunctions = []
        self.deletedFunctions = []

        self.addedClasses = []
        self.modifiedClasses = []
        self.deletedClasses = []

        self.addedInterfaces = []
        self.modifiedInterfaces = []
        self.deletedInterfaces = []

        self.addedTypes = []
        self.modifiedTypes = []
        self.deletedTypes = []

        self.addedEnums = []
        self.modifiedEnums = []
        self.deletedEnums = []

    def to_dict(self):
        """Converts the object to a dictionary for JSON serialization."""
        return {
            "moduleName": self.moduleName,
            "addedFunctions": self.addedFunctions, "modifiedFunctions": self.modifiedFunctions, "deletedFunctions": self.deletedFunctions,
            "addedClasses": self.addedClasses, "modifiedClasses": self.modifiedClasses, "deletedClasses": self.deletedClasses,
            "addedInterfaces": self.addedInterfaces, "modifiedInterfaces": self.modifiedInterfaces, "deletedInterfaces": self.deletedInterfaces,
            "addedTypes": self.addedTypes, "modifiedTypes": self.modifiedTypes, "deletedTypes": self.deletedTypes,
            "addedEnums": self.addedEnums, "modifiedEnums": self.modifiedEnums, "deletedEnums": self.deletedEnums,
        }

    def __str__(self):
        parts = []
        if self.addedFunctions or self.modifiedFunctions or self.deletedFunctions:
            parts.append(f"Functions: +{len(self.addedFunctions)} ~{len(self.modifiedFunctions)} -{len(self.deletedFunctions)}")
        if self.addedClasses or self.modifiedClasses or self.deletedClasses:
            parts.append(f"Classes: +{len(self.addedClasses)} ~{len(self.modifiedClasses)} -{len(self.deletedClasses)}")
        if self.addedInterfaces or self.modifiedInterfaces or self.deletedInterfaces:
            parts.append(f"Interfaces: +{len(self.addedInterfaces)} ~{len(self.modifiedInterfaces)} -{len(self.deletedInterfaces)}")
        if self.addedTypes or self.modifiedTypes or self.deletedTypes:
            parts.append(f"Types: +{len(self.addedTypes)} ~{len(self.modifiedTypes)} -{len(self.deletedTypes)}")
        if self.addedEnums or self.modifiedEnums or self.deletedEnums:
            parts.append(f"Enums: +{len(self.addedEnums)} ~{len(self.modifiedEnums)} -{len(self.deletedEnums)}")
        
        return f"Module: {self.moduleName}\n" + "\n".join(parts)

class TypeScriptFileDiff:
    """Analyzes and compares two TypeScript ASTs for semantic differences."""
    def __init__(self, module_name=""):
        self.changes = DetailedChanges(module_name)

    def get_decl_name(self, node: Node) -> str:
        """Finds the name of a TypeScript declaration."""
        # Handle `export` statements by looking inside them
        if node.type == 'export_statement':
            # FIX: Use named_child(...) instead of last_named_child
            if node.named_child_count > 0:
                declaration_node = node.named_child(node.named_child_count - 1)
                if declaration_node:
                    return self.get_decl_name(declaration_node)

        # Handle `const myFunc = () => {}`
        if node.type == 'lexical_declaration':
            # The structure is lexical_declaration -> variable_declarator -> name
            declarator = node.child_by_field_name('declarator')
            if declarator:
                name_node = declarator.child_by_field_name('name')
                if name_node:
                    return name_node.text.decode('utf8')

        # Handle `function`, `class`, `interface`, etc.
        name_node = node.child_by_field_name('name')
        if name_node:
            return name_node.text.decode('utf8')

        return None

    def extract_components(self, root: Node):
        """Extracts all top-level declarations from a TypeScript AST."""
        functions, classes, interfaces, types, enums = {}, {}, {}, {}, {}
        
        node_type_map = {
            'function_declaration': functions,
            'class_declaration': classes,
            'interface_declaration': interfaces,
            'type_alias_declaration': types,
            'enum_declaration': enums,
            'lexical_declaration': functions, # For const/let arrow functions
        }
        
        declarations = []
        if root.type == 'program':
            declarations = root.children

        for child in declarations:
            node_to_process = child
            
            if child.type == 'export_statement':
                if child.named_child_count > 0:
                    declaration_node = child.named_child(child.named_child_count - 1)
                    if declaration_node:
                        node_to_process = declaration_node
            
            node_type = node_to_process.type
            if node_type in node_type_map:
                if node_type == 'lexical_declaration':
                    declarator = node_to_process.named_child(0)
                    if not declarator or 'arrow_function' not in [c.type for c in declarator.children]:
                        continue 

                name = self.get_decl_name(child)
                if name:
                    target_dict = node_type_map[node_type]
                    target_dict[name] = (child, child.text.decode(errors="ignore"), child.start_point, child.end_point)

        return functions, classes, interfaces, types, enums

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
        """The main method to compare two TypeScript files."""
        old_funcs, old_classes, old_ifaces, old_types, old_enums = self.extract_components(old_file_ast.root_node)
        new_funcs, new_classes, new_ifaces, new_types, new_enums = self.extract_components(new_file_ast.root_node)

        # Diff all component types
        funcs_diff = self.diff_components(old_funcs, new_funcs)
        self.changes.addedFunctions, self.changes.deletedFunctions, self.changes.modifiedFunctions = funcs_diff["added"], funcs_diff["deleted"], funcs_diff["modified"]
        
        classes_diff = self.diff_components(old_classes, new_classes)
        self.changes.addedClasses, self.changes.deletedClasses, self.changes.modifiedClasses = classes_diff["added"], classes_diff["deleted"], classes_diff["modified"]

        ifaces_diff = self.diff_components(old_ifaces, new_ifaces)
        self.changes.addedInterfaces, self.changes.deletedInterfaces, self.changes.modifiedInterfaces = ifaces_diff["added"], ifaces_diff["deleted"], ifaces_diff["modified"]
        
        types_diff = self.diff_components(old_types, new_types)
        self.changes.addedTypes, self.changes.deletedTypes, self.changes.modifiedTypes = types_diff["added"], types_diff["deleted"], types_diff["modified"]
        
        enums_diff = self.diff_components(old_enums, new_enums)
        self.changes.addedEnums, self.changes.deletedEnums, self.changes.modifiedEnums = enums_diff["added"], enums_diff["deleted"], enums_diff["modified"]
        return self.changes

def print_ast_structure(node: Node, indent="    "):
    """
    Recursively prints the structure of an AST node.
    """
    # Print the current node's type and its position in the source code
    node_info = f"{indent} {node.type}"
    
    # If the node is a leaf (has no children), also print its text content
    if not node.children:
        node_info += f", Text: '{node.text.decode('utf8')}'"
    
    print(node_info)

    # Recursively call this function for each child node
    for child in node.children:
        print_ast_structure(child, indent + "  ")
        
# Main execution block
if __name__ == "__main__":
    # Load the TypeScript language
    TS_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
    parser = Parser(TS_LANGUAGE)

    # --- BEFORE ---
    file1_content = """
export function greet(name: string): string {
  return `Hello, ${name}`;
}

export interface User {
  id: number;
  name: string;
}

// Type to be deleted
type Status = 'active' | 'inactive';

export class ApiClient {
  constructor(private baseUrl: string) {}
}

enum LogLevel {
  INFO,
  WARN
}
"""

    # --- AFTER ---
    file2_content = """
export function greet(name: string, title?: string): string {
  const greeting = title ? `${title} ${name}` : name;
  return `Hello, ${greeting}!`; // Modified function
}

export interface User {
  id: string; // Modified interface
  name: string;
  email?: string;
}

// Added new arrow function
export const farewell = (name: string) => `Goodbye, ${name}`;

// Deleted type Status

// Class ApiClient was deleted

// Added new type
export type ApiResponse<T> = { success: boolean, data: T };

// Modified enum
enum LogLevel {
  INFO,
  WARN,
  ERROR
}
"""
    ast1 = parser.parse(bytes(file1_content, "utf8"))
    ast2 = parser.parse(bytes(file2_content, "utf8"))
    
    print_ast_structure(ast1.root_node, "AST 1 Structure")
    print_ast_structure(ast2.root_node, "AST 2 Structure")
    differ = TypeScriptFileDiff("api.ts")
    changes = differ.compare_two_files(ast1, ast2)

    print("--- FINAL SUMMARY ---")
    print(changes)
    
    print("\n--- FINAL JSON OUTPUT ---")
    print(json.dumps(changes.to_dict(), indent=2))

