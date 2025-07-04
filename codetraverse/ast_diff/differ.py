import subprocess
import json
import re
from collections import defaultdict
from tree_sitter import Language, Parser, Node
import tree_sitter_rescript
import hashlib
import os


class DetailedChanges:
    def __init__(self, module_name):
        self.moduleName = module_name
        self.addedFunctions = []
        self.modifiedFunctions = []
        self.deletedFunctions = []

        self.addedTypes = []
        self.modifiedTypes = []
        self.deletedTypes = []

        self.addedExternals = []
        self.modifiedExternals = []
        self.deletedExternals = []

        self.addedImports = []
        self.modifiedImports = []
        self.deletedImports = []

    def to_dict(self):
        return {
            "moduleName": self.moduleName,
            "addedFunctions": self.addedFunctions,
            "modifiedFunctions": self.modifiedFunctions,
            "deletedFunctions": self.deletedFunctions,
            "addedTypes": self.addedTypes,
            "modifiedTypes": self.modifiedTypes,
            "deletedTypes": self.deletedTypes,
            "addedExternals": self.addedExternals,
            "modifiedExternals": self.modifiedExternals,
            "deletedExternals": self.deletedExternals,
        }

    def __str__(self):
        return (
            f"Module: {self.moduleName}\n"
            f"Added Functions: {self.addedFunctions}\n"
            f"Modified Functions: {self.modifiedFunctions}\n"
            f"Deleted Functions: {self.deletedFunctions}\n"
            f"Added Types: {self.addedTypes}\n"
            f"Modified Types: {self.modifiedTypes}\n"
            f"Deleted Types: {self.deletedTypes}\n"
            f"Added Externals: {self.addedExternals}\n"
            f"Modified Externals: {self.modifiedExternals}\n"
            f"Deleted Externals: {self.deletedExternals}"
        )


def format_rescript_file(file_pth):
    try:
        subprocess.run(["npx", "rescript", "format", file_pth], capture_output=True)
    except:
        pass


class RescriptFileDiff:
    def __init__(self, module_name=""):
        self.changes = DetailedChanges(module_name)

    def get_decl_name(self, node: Node, node_type: str, name_type: str) -> str:
        for child in node.children:
            if node_type and child.type == node_type:
                for grandchild in child.children:
                    if grandchild.is_named and grandchild.type == name_type:
                        return grandchild.text.decode(errors="ignore")
            elif not node_type and child.is_named and child.type == name_type:
                return child.text.decode(errors="ignore")
        return None

    def deep_equal(self, nodeA: Node, nodeB: Node):
        if (nodeA is None) != (nodeB is None):
            return False

        if nodeA is None and nodeB is None:
            return True

        if nodeA.type != nodeB.type:
            return False

        childrenA = nodeA.children
        childrenB = nodeB.children

        if len(childrenA) != len(childrenB):
            return False

        if len(childrenA) == 0:
            return nodeA.text == nodeB.text and nodeA.parent.text == nodeB.parent.text

        for childA, childB in zip(childrenA, childrenB):
            if not self.deep_equal(childA, childB):
                return False

        return True

    def extract_components(self, root: Node):
        queue = [root]
        
        functions = {}
        types = {}
        externals = {}

        node_name_mapper = {
            "let_declaration": (functions, lambda x: self.get_decl_name(x, "let_binding", "value_identifier")),
            "type_declaration": (types, lambda x: self.get_decl_name(x, "type_binding", "type_identifier")),
            "external_declaration": (externals, lambda x: self.get_decl_name(x, None, "value_identifier"))
        }

        while queue:
            current_node = queue.pop()
            if current_node.type in node_name_mapper.keys():
                dct, mapper_function = node_name_mapper[current_node.type]
                name = mapper_function(current_node)
                if name:
                    if current_node.parent.type != "source_file":
                        try:
                            name = f"{current_node.parent.parent.child(0).text.decode()}::{name}"
                        except:
                            pass
                    dct[name] = (current_node, current_node.text.decode(errors="ignore"), current_node.start_point, current_node.end_point)
            else:
                for child in reversed(current_node.children):
                    if child.is_named:
                        queue.append(child)
        return functions, types, externals

    def diff_components(self, before_map: dict, after_map: dict) -> dict:
        before_names = set(before_map.keys())
        after_names = set(after_map.keys())

        added_names = after_names - before_names
        deleted_names = before_names - after_names
        common = before_names & after_names

        added = [(n, after_map[n][1], {"start": after_map[n][2], "end": after_map[n][3]}) for n in sorted(added_names)]
        deleted = [(n, before_map[n][1], {"start": before_map[n][2], "end": before_map[n][3]}) for n in sorted(deleted_names)]

        modified = []
        for name in sorted(common):
            old_ast, old_body, old_start, old_end = before_map[name]
            new_ast, new_body, new_start, new_end = after_map[name]
            if not self.deep_equal(old_ast, new_ast):
                modified.append((name, old_body, new_body, {"old_start": old_start, "old_end": old_end, "new_start": new_start, "new_end": new_end}))

        return {"added": added, "deleted": deleted, "modified": modified}

    def compare_two_files(self, old_file_ast, new_file_ast) -> DetailedChanges:
        old_funcs, old_types, old_ext = self.extract_components(old_file_ast.root_node)
        new_funcs, new_types, new_ext = self.extract_components(new_file_ast.root_node)

        funcs_diff = self.diff_components(old_funcs, new_funcs)
        self.changes.addedFunctions = funcs_diff["added"]
        self.changes.deletedFunctions = funcs_diff["deleted"]
        self.changes.modifiedFunctions = funcs_diff["modified"]

        types_diff = self.diff_components(old_types, new_types)
        self.changes.addedTypes = types_diff["added"]
        self.changes.deletedTypes = types_diff["deleted"]
        self.changes.modifiedTypes = types_diff["modified"]

        ext_diff = self.diff_components(old_ext, new_ext)
        self.changes.addedExternals = ext_diff["added"]
        self.changes.deletedExternals = ext_diff["deleted"]
        self.changes.modifiedExternals = ext_diff["modified"]

        return self.changes

    def process_single_file(self, file_ast, mode="deleted"):
        funcs, types, exts = self.extract_components(file_ast.root_node)
        func_names = set(funcs.keys())
        type_names = set(types.keys())
        ext_names = set(exts.keys())

        if mode == "deleted":
            self.changes.deletedFunctions = [(n, funcs[n][1], {"start": funcs[n][2], "end": funcs[n][3]}) for n in sorted(func_names)]
            self.changes.deletedTypes = [(n, types[n][1], {"start": types[n][2], "end": types[n][3]}) for n in sorted(type_names)]
            self.changes.deletedExternals = [(n, exts[n][1], {"start": exts[n][2], "end": exts[n][3]}) for n in sorted(ext_names)]
        else:
            self.changes.addedFunctions = [(n, funcs[n][1], {"start": funcs[n][2], "end": funcs[n][3]}) for n in sorted(func_names)]
            self.changes.addedTypes = [(n, types[n][1], {"start": types[n][2], "end": types[n][3]}) for n in sorted(type_names)]
            self.changes.addedExternals = [(n, exts[n][1], {"start": exts[n][2], "end": exts[n][3]}) for n in sorted(ext_names)]
        
        return self.changes

# if __name__ == "__main__":
#     RS_LANGUAGE = Language(tree_sitter_rescript.language())
#     parser = Parser(RS_LANGUAGE)
#     with open("file1.res", "rb") as f, open("file2.res", "rb") as f2:
#         content1 = f.read()
#         content2 = f2.read()
#     ast = parser.parse(content1)
#     ast2 = parser.parse(content2)
#     differ = RescriptFileDiff("fred")

#     print(differ.compare_two_files(ast, ast2))