# purescript_extractor.py

import os
import json
import html
import chardet
from bs4 import BeautifulSoup
from tree_sitter_language_pack import get_parser
from codetraverse.base.component_extractor import ComponentExtractor

def parse_html_to_text(file_path: str) -> str:
    """
    Read a .purs file, detect its encoding, strip any HTML markup,
    and return clean UTF-8 source text.
    """
    with open(file_path, "rb") as f:
        raw = f.read()
    guess    = chardet.detect(raw)
    encoding = guess.get("encoding") or "utf-8"
    text     = raw.decode(encoding, errors="replace")
    soup     = BeautifulSoup(text, "html.parser")
    return html.unescape(soup.get_text(separator="\n"))


class PureScriptComponentExtractor(ComponentExtractor):
    def __init__(self):
        # Prepare a Tree-Sitter parser for PureScript
        self.parser        = get_parser("purescript")
        self.all_components = []

    def parse_file(self, file_path: str):
        plain = parse_html_to_text(file_path)
        tree  = self.parser.parse(plain.encode("utf-8"))
        return plain, tree

    def get_text(self, node, plain: str) -> str:
        """
        Extract the exact source snippet for a given AST node.
        """
        b = plain.encode("utf-8")
        return b[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def extract_imports(self, root, plain: str) -> dict:
        """
        Build a map { importedName → moduleName } for top-level imports.
        """
        mapping = {}
        for node in root.children:
            if node.type != "import":
                continue

            # module path: Control.Monad.Eff → Control/Monad/Eff.purs
            qm = next((c for c in node.children if c.type == "qualified_module"), None)
            if not qm:
                continue
            module_name = ".".join(
                self.get_text(c, plain).strip()
                for c in qm.children
                if c.type == "module"
            )

            # named imports within import_list
            imp_list = next((c for c in node.children if c.type == "import_list"), None)
            if imp_list:
                for item in imp_list.children:
                    if item.type != "import_item":
                        continue
                    spec = next(
                        (c for c in item.children if c.type in ("var_import", "type_import")),
                        None
                    )
                    if spec:
                        name_node = next(
                            (c for c in spec.children if c.type in ("variable", "type")),
                            None
                        )
                        if name_node:
                            name = self.get_text(name_node, plain).strip()
                            mapping[name] = module_name

            # alias via `as`
            for i, c in enumerate(node.children):
                if c.type == "as" and i + 1 < len(node.children):
                    alias_node = node.children[i+1]
                    if alias_node.type == "module":
                        alias = self.get_text(alias_node, plain).strip()
                        mapping[alias] = module_name

        return mapping

    def extract_type_dependencies(self, node, plain: str) -> list:
        """
        Iteratively collect all type names under `node`.
        """
        deps  = set()
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type in ("type_name", "qualified_type"):
                deps.add(self.get_text(n, plain).strip())
            stack.extend(n.children)
        return list(deps)

    def extract_function_calls(self, node, plain: str, module: str, imports: dict) -> list:
        """
        Iteratively find every `exp_apply` call, resolve it to "<module>::<fn>".
        """
        calls = []
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "exp_apply":
                fn  = n.children[0]
                txt = self.get_text(fn, plain).strip()
                # print("siraj",txt)
                if "." in txt:
                    alias, method = txt.split(".",1)
                    target_mod = imports.get(alias, alias)
                    callee     = f"{target_mod}::{method}"
                    if "logRejectedPromise" in callee:
                        print(f"DEBUG1: {callee} {target_mod} {method}")
                    # print(callee, target_mod, method)
                    base_name  = method
                else:
                    target_mod = imports.get(txt, module)
                    # print(txt, "#########",imports)     #     debugging lines for having functions from the typescript
                    # if txt not in imports:
                    #     print(f"WARNING: {txt} not found in imports, using module {module}",imports  )
                    callee     = f"{target_mod}::{txt}"
                    # print(callee, target_mod, txt)
                    base_name  = txt

                calls.append({
                    "name":            txt,
                    "base_name":       base_name,
                    "resolved_callee": callee
                })
            stack.extend(n.children)
        return calls

    def process_node(self,
                     node,
                     plain: str,
                     file_path: str,
                     root_folder: str,
                     imports: dict,
                     module: str,
                     sig_map: dict) -> list:
        """
        Emit component dicts for this node, inlining signatures into functions.
        """
        comps = []
        rel   = os.path.relpath(file_path, root_folder).replace("\\","/")

        # ── foreign import ─────────────────────────
        if node.type == "foreign_import":
            code       = self.get_text(node, plain)
            is_data    = any(c.type == "data" for c in node.children)
            # name = first identifier/type_identifier child
            name_node  = next((c for c in node.children
                               if c.type in ("identifier","type_identifier")), None)
            name       = self.get_text(name_node, plain).strip() if name_node else None
            # signature = everything after the "::" token
            saw_sep    = False
            parts      = []
            for c in node.children:
                if saw_sep:
                    parts.append(self.get_text(c, plain))
                elif self.get_text(c, plain).strip() == "::":
                    saw_sep = True
            signature = "".join(parts).strip()

            comps.append({
                "kind":           "foreign_data" if is_data else "foreign_import",
                "module":         module or rel,
                "name":           name,
                "type_signature": signature,
                "start_line":     node.start_point[0] + 1,
                "end_line":       node.end_point[0] + 1,
                "code":           code,
                "file_path":      rel
            })
            return comps

        # ── skip standalone signature ──────────────
        if node.type == "signature":
            return comps

        # ── import ─────────────────────────────────
        if node.type == "import":
            snippet = self.get_text(node, plain)
            if snippet.strip() != "import":
                comps.append({
                    "kind":       "import",
                    "module":     module or rel,
                    "start_line": node.start_point[0] + 1,
                    "end_line":   node.end_point[0] + 1,
                    "jsdoc":      None,
                    "code":       snippet,
                    "file_path":  rel
                })
            return comps

        # ── function binding ───────────────────────
        if node.type == "function":
            name = self.get_text(node.children[0], plain).strip()
            # parameters block
            params = []
            pat_blk = next((c for c in node.children if c.type=="patterns"), None)
            if pat_blk:
                for p in pat_blk.children:
                    if p.type=="pat_name":
                        params.append(self.get_text(p, plain).strip())
            calls = self.extract_function_calls(node, plain, module or rel, imports)
            tdeps = self.extract_type_dependencies(node, plain)
            # inline signature if present
            sig  = sig_map.get(name)
            body = self.get_text(node, plain)
            code = f"{sig}\n{body}" if sig else body

            comps.append({
                "kind":             "function",
                "module":           module or rel,
                "name":             name,
                "type_signature":   sig or None,
                "parameters":       params,
                "function_calls":   calls,
                "type_dependencies":tdeps,
                "start_line":       node.start_point[0] + 1,
                "end_line":         node.end_point[0] + 1,
                "code":             code,
                "file_path":        rel
            })
            return comps

        # ── type alias ─────────────────────────────
        if node.type == "type_alias_declaration":
            alias = self.get_text(node.children[1], plain).strip()
            tdeps = self.extract_type_dependencies(node, plain)
            comps.append({
                "kind":             "type_alias",
                "module":           module or rel,
                "name":             alias,
                "type_dependencies":tdeps,
                "start_line":       node.start_point[0] + 1,
                "end_line":         node.end_point[0] + 1,
                "code":             self.get_text(node, plain),
                "file_path":        rel
            })
            return comps

        # ── data declaration ───────────────────────
        if node.type == "data_declaration":
            name = ""
            if len(node.children)>1:
                name = self.get_text(node.children[1], plain).strip()
            ctors = [
                self.get_text(c, plain).strip()
                for c in node.children if c.type=="constructor"
            ]
            comps.append({
                "kind":         "data_declaration",
                "module":       module or rel,
                "name":         name,
                "constructors": ctors,
                "start_line":   node.start_point[0] + 1,
                "end_line":     node.end_point[0] + 1,
                "code":         self.get_text(node, plain),
                "file_path":    rel,
            })
            return comps

                # ── kind_value_declaration ────────────────────
        if node.type == "kind_value_declaration":
            code    = self.get_text(node, plain)
            start   = node.start_point[0] + 1
            end     = node.end_point[0]   + 1
            # first identifier or type_identifier child
            name_n  = next((c for c in node.children if c.type in ("identifier","type_identifier")), None)
            name    = self.get_text(name_n, plain).strip() if name_n else None
            # everything after "::"
            saw_sep = False
            parts   = []
            for c in node.children:
                if saw_sep:
                    parts.append(self.get_text(c, plain))
                elif self.get_text(c, plain).strip() == "::":
                    saw_sep = True
            signature = "".join(parts).strip()

            comps.append({
                "kind":           "foreign_data",
                "module":         module or rel,
                "name":           name,
                "type_signature": signature,
                "start_line":     start,
                "end_line":       end,
                "code":           code,
                "file_path":      rel
            })
            return comps

        # ── newtype ────────────────────────────────────
        if node.type == "newtype":
            code = self.get_text(node, plain)
            start = node.start_point[0] + 1
            end   = node.end_point[0]   + 1
            # try to find the declared type name in a named field
            name_n = node.child_by_field_name("type")
            # if that fails, fall back to the 2nd child (if it exists)
            if name_n is None and len(node.children) > 1:
                name_n = node.children[1]
            name = self.get_text(name_n, plain).strip() if name_n else None

            # 1) emit the “newtype” node
            comps.append({
                "kind":        "newtype",
                "module":      module or rel,
                "name":        name,
                "start_line":  start,
                "end_line":    end,
                "code":        code,
                "file_path":   rel
            })

            # 2) also emit it as a data_declaration with its constructors
            ctors = [
                self.get_text(c, plain).strip()
                for c in node.children
                if c.type == "constructor"
            ]
            comps.append({
                "kind":         "data_declaration",
                "module":       module or rel,
                "name":         name,
                "constructors": ctors,
                "start_line":   start,
                "end_line":     end,
                "code":         code,
                "file_path":    rel
            })

            return comps


        # ── derive_declaration ────────────────────────
        if node.type == "derive_declaration":
            code = self.get_text(node, plain)
            comps.append({
                "kind":        "derive_declaration",
                "module":      module or rel,
                "code":        code,
               "start_line":  node.start_point[0] + 1,
                "end_line":    node.end_point[0]   + 1,
                "file_path":   rel
            })
            return comps

        # ── type_alias (node.type == "type_alias") ───
        if node.type == "type_alias":
            code  = self.get_text(node, plain)
            name  = self.get_text(node.children[1], plain).strip()
            tdeps = self.extract_type_dependencies(node, plain)

            comps.append({
                "kind":             "type_alias",
                "module":           module or rel,
                "name":             name,
                "type_dependencies": tdeps,
                "start_line":       node.start_point[0] + 1,
                "end_line":         node.end_point[0]   + 1,
                "code":             code,
                "file_path":        rel
            })
            return comps

        # ── class_declaration ─────────────────────────
        if node.type == "class_declaration":
            # 1) raw text, span
            code      = self.get_text(node, plain)
            start     = node.start_point[0] + 1
            end       = node.end_point[0] + 1
            rel       = os.path.relpath(file_path, root_folder).replace("\\","/")

            # 2) class name
            #    grammar: (class_declaration (class_head (class_name ...) ... ) (class_body ...))
            head      = next((c for c in node.children if c.type == "class_head"), None)
            name_node = None
            if head:
                name_node = next((c for c in head.children if c.type == "class_name"), None)
            class_name = self.get_text(name_node, plain).strip() if name_node else None

            # 3) type parameters
            type_params = []
            if head:
                for tv in head.children:
                    if tv.type == "type_variable":
                        type_params.append(self.get_text(tv, plain).strip())

            # 4) functional dependencies (fundeps)
            fundeps = []
            if head:
                fnode = next((c for c in head.children if c.type == "fundeps"), None)
                if fnode:
                    for fd in fnode.children:
                        if fd.type == "fundep":
                            fundeps.append(self.get_text(fd, plain).strip())

            # 5) collect methods (signatures) from the body
            methods = []
            body = next((c for c in node.children if c.type == "class_body"), None)
            if body:
                for m in body.children:
                    # only signatures define methods in a PureScript typeclass
                    if m.type == "signature":
                        # each signature’s first child is the method name
                        mn = m.children[0]
                        mname = self.get_text(mn, plain).strip()
                        fq    = f"{module or rel}::{class_name}.{mname}"   # replace
                        methods.append(fq)

            # 6) emit one single class component with has_methods
            comps.append({
                "kind":           "class",
                "module":         module or rel,
                "name":           class_name,
                "type_parameters":type_params or None,
                "fundeps":        fundeps or None,
                "start_line":     start,
                "end_line":       end,
                "code":           code,
                "file_path":      rel,
                "has_methods":    methods
            })
            return comps


        # ── class_instance ────────────────────────────
        if node.type == "class_instance":
            code      = self.get_text(node, plain)
            name_node = node.child_by_field_name("instance_name")
            name      = self.get_text(name_node, plain).strip() if name_node else None

            comps.append({
                "kind":        "instance",
                "module":      module or rel,
                "name":        name,
                "start_line":  node.start_point[0] + 1,
                "end_line":    node.end_point[0]   + 1,
                "code":        code,
                "file_path":   rel
            })
            return comps

        # ── pattern_synonym ───────────────────────────
        if node.type == "pattern_synonym":
            code     = self.get_text(node, plain)
            pat      = node.child_by_field_name("pattern")
            name     = self.get_text(pat, plain).strip() if pat else None
            sig_node = next((c for c in node.children if c.type=="signature"), None)
            sig_txt  = self.get_text(sig_node, plain).strip() if sig_node else None

            comps.append({
                "kind":           "pattern_synonym",
               "module":         module or rel,
                "name":           name,
                "type_signature": sig_txt,
                "start_line":     node.start_point[0] + 1,
                "end_line":       node.end_point[0]   + 1,
                "code":           code,
                "file_path":      rel
            })
            return comps

        return comps

    def extract_from_file(self, file_path: str, root_folder: str) -> list:
        plain, tree = self.parse_file(file_path)
        root        = tree.root_node

        # 1) collect all top-level signatures
        sig_map = {}
        for c in root.children:
            if c.type == "signature":
                raw = self.get_text(c, plain)
                if "::" in raw:
                    fn, rest = raw.split("::",1)
                    sig_map[fn.strip()] = raw.strip()

        # 2) determine module name, if any
        module = None
        for c in root.children:
            if c.type == "qualified_module":
                parts = [
                    self.get_text(ch, plain).strip()
                    for ch in c.children if ch.type=="module"
                ]
                module = ".".join(parts) if parts else None
                break

        # 3) collect imports
        imports = self.extract_imports(root, plain)
        # print("siraj imports", imports)

        # 4) iterative pre-order walk
        components = []
        stack      = [root]
        while stack:
            node = stack.pop()
            components += self.process_node(
                node, plain, file_path, root_folder, imports, module, sig_map
            )
            for child in reversed(node.children):
                stack.append(child)

        # 5) normalize & JSON-filter
        rel = os.path.relpath(file_path, root_folder).replace("\\","/")
        out = []
        for comp in components:
            # file_path already set in process_node
            try:
                json.dumps(comp)
                out.append(comp)
            except:
                pass

        return out

    def process_file(self, file_path: str):
        """
        Called by main.py for each .purs file.
        """
        root_folder        = os.environ.get("ROOT_DIR", "")
        self.all_components = self.extract_from_file(file_path, root_folder)

    def write_to_file(self, output_path: str):
        """
        Dump components as JSON.
        """
        serializable = []
        for comp in self.all_components:
            try:
                json.dumps(comp)
                serializable.append(comp)
            except:
                pass
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)

    def extract_all_components(self) -> list:
        return self.all_components
