import json
from tree_sitter import Language, Parser, Node
import tree_sitter_rust

class DetailedChanges:
    """A data class to hold the results of a diff operation for Rust."""
    def __init__(self, module_name):
        self.moduleName = module_name
        self.addedFunctions = []
        self.modifiedFunctions = []
        self.deletedFunctions = []
        self.addedStructs = []
        self.modifiedStructs = []
        self.deletedStructs = []
        self.addedEnums = []
        self.modifiedEnums = []
        self.deletedEnums = []
        self.addedTraits = []
        self.modifiedTraits = []
        self.deletedTraits = []
        self.addedImpls = []
        self.modifiedImpls = []
        self.deletedImpls = []
        self.addedUses = []
        self.modifiedUses = []
        self.deletedUses = []
        self.addedConsts = []
        self.modifiedConsts = []
        self.deletedConsts = []

    def to_dict(self):
        """Converts the object to a dictionary for JSON serialization."""
        return {
            "moduleName": self.moduleName,
            "addedFunctions": self.addedFunctions, "modifiedFunctions": self.modifiedFunctions, "deletedFunctions": self.deletedFunctions,
            "addedStructs": self.addedStructs, "modifiedStructs": self.modifiedStructs, "deletedStructs": self.deletedStructs,
            "addedEnums": self.addedEnums, "modifiedEnums": self.modifiedEnums, "deletedEnums": self.deletedEnums,
            "addedTraits": self.addedTraits, "modifiedTraits": self.modifiedTraits, "deletedTraits": self.deletedTraits,
            "addedImpls": self.addedImpls, "modifiedImpls": self.modifiedImpls, "deletedImpls": self.deletedImpls,
            "addedUses": self.addedUses, "modifiedUses": self.modifiedUses, "deletedUses": self.deletedUses,
            "addedConsts": self.addedConsts, "modifiedConsts": self.modifiedConsts, "deletedConsts": self.deletedConsts,
        }

    def __str__(self):
        parts = []
        if self.addedFunctions or self.modifiedFunctions or self.deletedFunctions:
            parts.append(f"Functions: +{len(self.addedFunctions)} ~{len(self.modifiedFunctions)} -{len(self.deletedFunctions)}")
        if self.addedStructs or self.modifiedStructs or self.deletedStructs:
            parts.append(f"Structs: +{len(self.addedStructs)} ~{len(self.modifiedStructs)} -{len(self.deletedStructs)}")
        if self.addedEnums or self.modifiedEnums or self.deletedEnums:
            parts.append(f"Enums: +{len(self.addedEnums)} ~{len(self.modifiedEnums)} -{len(self.deletedEnums)}")
        if self.addedTraits or self.modifiedTraits or self.deletedTraits:
            parts.append(f"Traits: +{len(self.addedTraits)} ~{len(self.modifiedTraits)} -{len(self.deletedTraits)}")
        if self.addedImpls or self.modifiedImpls or self.deletedImpls:
            parts.append(f"Impls: +{len(self.addedImpls)} ~{len(self.modifiedImpls)} -{len(self.deletedImpls)}")
        if self.addedUses or self.modifiedUses or self.deletedUses:
            parts.append(f"Uses: +{len(self.addedUses)} ~{len(self.modifiedUses)} -{len(self.deletedUses)}")
        if self.addedConsts or self.modifiedConsts or self.deletedConsts:
            parts.append(f"Consts: +{len(self.addedConsts)} ~{len(self.modifiedConsts)} -{len(self.deletedConsts)}")
        return f"Module: {self.moduleName}\n" + "\n".join(parts)

class RustFileDiff:
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
            _, old_body, _, _ = before_map[name]
            _, new_body, old_start, old_end = after_map[name]
            if old_body.strip() != new_body.strip():
                 modified.append((name, old_body, new_body, {"old_start": old_start, "old_end": old_end}))
        return {"added": added, "deleted": deleted, "modified": modified}

    def compare_two_files(self, old_file_ast: Node, new_file_ast: Node) -> DetailedChanges:
        """The main method to compare two Rust files."""
        old_items = self.extract_components(old_file_ast.root_node)
        new_items = self.extract_components(new_file_ast.root_node)

        # Diff all component types
        funcs_diff = self.diff_components(old_items["functions"], new_items["functions"])
        self.changes.addedFunctions, self.changes.deletedFunctions, self.changes.modifiedFunctions = funcs_diff["added"], funcs_diff["deleted"], funcs_diff["modified"]
        
        structs_diff = self.diff_components(old_items["structs"], new_items["structs"])
        self.changes.addedStructs, self.changes.deletedStructs, self.changes.modifiedStructs = structs_diff["added"], structs_diff["deleted"], structs_diff["modified"]

        enums_diff = self.diff_components(old_items["enums"], new_items["enums"])
        self.changes.addedEnums, self.changes.deletedEnums, self.changes.modifiedEnums = enums_diff["added"], enums_diff["deleted"], enums_diff["modified"]

        traits_diff = self.diff_components(old_items["traits"], new_items["traits"])
        self.changes.addedTraits, self.changes.deletedTraits, self.changes.modifiedTraits = traits_diff["added"], traits_diff["deleted"], traits_diff["modified"]
        
        impls_diff = self.diff_components(old_items["impls"], new_items["impls"])
        self.changes.addedImpls, self.changes.deletedImpls, self.changes.modifiedImpls = impls_diff["added"], impls_diff["deleted"], impls_diff["modified"]

        uses_diff = self.diff_components(old_items["uses"], new_items["uses"])
        self.changes.addedUses, self.changes.deletedUses, self.changes.modifiedUses = uses_diff["added"], uses_diff["deleted"], uses_diff["modified"]
        
        consts_diff = self.diff_components(old_items["consts"], new_items["consts"])
        self.changes.addedConsts, self.changes.deletedConsts, self.changes.modifiedConsts = consts_diff["added"], consts_diff["deleted"], consts_diff["modified"]

        return self.changes

if __name__ == "__main__":
    RUST_LANGUAGE = Language(tree_sitter_rust.language())
    parser = Parser(RUST_LANGUAGE)

    # --- BEFORE ---
    file1_content = """
use std::collections::HashMap; // To be modified
use std::time::Duration;      // To be deleted

const TIMEOUT_MS: u32 = 5000;
static RETRY_COUNT: u32 = 3;

// To be modified
struct User {
    id: u32,
}

// To be deleted
struct Guest {}

// To be modified
enum Status {
    Connected,
    Disconnected,
}

// To be deleted
enum Priority { High }

// To be modified
trait AsJson {
    fn to_json(&self) -> String;
}

// To be deleted
trait Loggable {}

// To be modified
impl AsJson for User {
    fn to_json(&self) -> String {
        format!("{{\"id\": {}}}", self.id)
    }
}

// To be deleted
impl Loggable for User {}

// To be modified
fn get_user(id: u32) -> User {
    User { id }
}

// To be deleted
fn is_connected() -> bool {
    true
}
"""

    # --- AFTER ---
    file2_content = """
use std::collections::{HashMap, HashSet}; // Modified
use std::path::Path;                     // Added

const TIMEOUT_MS: u32 = 10000;      // Modified
const VERSION: &str = "1.1.0";      // Added
// RETRY_COUNT was deleted

// Modified
struct User {
    id: u32,
    name: String,
}

// Added
struct Admin {
    id: u32,
}
// Guest was deleted

// Modified
enum Status {
    Connected,
    Disconnected,
    Connecting,
}

// Added
enum Role { User, Admin }
// Priority was deleted

// Modified
trait AsJson {
    fn to_json(&self) -> String;
    fn from_json(s: &str) -> Self;
}

// Added
trait Displayable {}
// Loggable was deleted

// Modified
impl AsJson for User {
    fn to_json(&self) -> String {
        format!("{{\"id\": {}, \"name\": \"{}\"}}", self.id, self.name)
    }
}

// Added
impl Displayable for User {}
// impl Loggable for User was deleted

// Modified
fn get_user(id: u32, name: &str) -> User {
    User { id, name: String::from(name) }
}

// Added
fn get_admin(id: u32) -> Admin {
    Admin { id }
}
// is_connected was deleted
"""
    ast1 = parser.parse(bytes(file1_content, "utf8"))
    ast2 = parser.parse(bytes(file2_content, "utf8"))

    differ = RustFileDiff("lib.rs")
    changes = differ.compare_two_files(ast1, ast2)

    print("--- FINAL SUMMARY ---")
    print(changes)
    
    print("\n--- FINAL JSON OUTPUT ---")
    print(json.dumps(changes.to_dict(), indent=2))