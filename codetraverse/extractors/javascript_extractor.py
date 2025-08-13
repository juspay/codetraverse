import os
import re
import json
import html
import chardet
from typing import Dict, Any, List, Optional, Tuple, Set
from bs4 import BeautifulSoup
from tree_sitter_language_pack import get_parser
from codetraverse.base.component_extractor import ComponentExtractor


# ---------------------------
# Text / file helpers
# ---------------------------

def parse_html_to_text(file_path: str) -> str:
    with open(file_path, 'rb') as f:
        raw = f.read()
    guess = chardet.detect(raw)
    encoding = guess.get('encoding') or 'utf-8'
    text = raw.decode(encoding, errors='replace')
    # Strip HTML safely if present
    soup = BeautifulSoup(text, 'html.parser')
    plain = html.unescape(soup.get_text(separator='\n'))
    return plain


def norm_slashes(p: str) -> str:
    return p.replace("\\", "/")


def relpath_with_repo(file_path: str) -> str:
    """
    Return a forward-slashed path prefixed with the repo folder name.
    Example:
      ROOT_DIR=/home/me/projects/repo_name
      file_path=/home/me/projects/repo_name/src/utils/models.js
      -> "repo_name/src/utils/models.js"
    """
    fp = norm_slashes(file_path)
    root = os.environ.get("ROOT_DIR", "")
    if root:
        base = os.path.basename(os.path.normpath(root))  # "repo_name"
        try:
            rel = os.path.relpath(file_path, root)
        except Exception:
            rel = file_path
        return norm_slashes(os.path.join(base, rel))
    return fp


# ---------------------------
# Extractor
# ---------------------------

class JavascriptExtractor(ComponentExtractor):
    """
    Robust JavaScript component extractor backed by Tree-sitter (JS grammar).
    Produces components with clean paths, function/class/methods, imports/exports,
    and nested function call discovery with resolution hints.
    """

    JS_EXTS = (".js", ".mjs", ".cjs", ".jsx")

    def __init__(self):
        self.parser = get_parser("javascript")
        self.all_components: List[Dict[str, Any]] = []

    # ------------- Parsing & text -------------

    def parse_file(self, file_path: str) -> Tuple[str, Any]:
        plain = parse_html_to_text(file_path)
        tree = self.parser.parse(plain.encode("utf-8"))
        return plain, tree

    def get_text(self, node, plain: str) -> str:
        b = plain.encode("utf-8")
        return b[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    # ------------- Public API -------------

    def extract_all_components(self):
        return self.all_components

    def process_file(self, file_path: str):
        plain, tree = self.parse_file(file_path)

        # repo-prefixed, forward-slashed paths
        safe_file   = relpath_with_repo(os.path.abspath(file_path))
        module_name = safe_file
        root_folder = norm_slashes(os.path.dirname(os.path.abspath(file_path)))

        components = self._walk_node(
            node=tree.root_node,
            plain=plain,
            file_path=safe_file,
            module_name=module_name,
            root_folder=root_folder,
        )

        serializable = []
        for comp in components:
            comp["file_path"] = comp.get("file_path") or safe_file
            comp["module"]    = comp.get("module") or module_name
            try:
                json.dumps(comp)
                serializable.append(comp)
            except Exception:
                pass

        self.all_components = serializable

    def write_to_file(self, output_path: str):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    # ------------- Core tree walk -------------

    def _walk_node(self, node, plain: str, file_path: str, module_name: str, root_folder: str) -> List[Dict[str, Any]]:
        comps: List[Dict[str, Any]] = []

        # Functions
        if node.type in ("function_declaration", "generator_function_declaration"):
            comps.append(self._extract_function_like(node, plain, module_name, file_path, is_generator=("generator" in node.type)))

        # Arrow function attached to variable declarator
        if node.type == "arrow_function":
            parent = node.parent
            if parent and parent.type == "variable_declarator":
                name_node = parent.child_by_field_name("name")
                name = self.get_text(name_node, plain) if name_node else "<anon>"
                params_node = node.child_by_field_name("parameter") or node.child_by_field_name("parameters")
                params = self.get_text(params_node, plain) if params_node else "()"
                calls = self._extract_calls(node, plain, module_name, class_ctx=None, bases=None)
                comps.append({
                    "kind": "arrow_function",
                    "module": module_name,
                    "name": name,
                    "parameters": params,
                    "function_calls": calls,
                    "start_line": parent.start_point[0] + 1,
                    "end_line": parent.end_point[0] + 1,
                    "code": self.get_text(parent, plain),
                    "file_path": file_path
                })

        # Class + methods
        if node.type == "class_declaration":
            comps.extend(self._extract_class(node, plain, module_name, file_path))

        # Variable declarations (var / let / const)
        if node.type in ("variable_declaration", "lexical_declaration"):
            comps.extend(self._extract_variables(node, plain, module_name, file_path))

        # Imports/exports
        if node.type == "import_statement":
            comps.append(self._extract_import(node, plain, module_name, file_path))

        if node.type == "export_statement":
            comps.extend(self._extract_export(node, plain, module_name, file_path))

        # Statements & expressions — useful for structure/graph
        statement_kinds = {
            "if_statement": "if_statement",
            "for_statement": "for_statement",
            "while_statement": "while_statement",
            "do_statement": "do_statement",
            "switch_statement": "switch_statement",
            "try_statement": "try_statement",
            "throw_statement": "throw_statement",
            "debugger_statement": "debugger_statement",
            "with_statement": "with_statement",
            "break_statement": "break_statement",
            "continue_statement": "continue_statement",
            "return_statement": "return_statement",
            "empty_statement": "empty_statement",
            "labeled_statement": "labeled_statement",
        }
        if node.type in statement_kinds:
            comp = {
                "kind": statement_kinds[node.type],
                "module": module_name,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "code": self.get_text(node, plain),
                "file_path": file_path
            }
            # enrich with key fields if present
            if node.type == "if_statement":
                cond = node.child_by_field_name("condition")
                comp["condition"] = self.get_text(cond, plain) if cond else None
            if node.type == "for_statement":
                comp["initializer"] = self._safe_text(node.child_by_field_name("initializer"), plain)
                comp["condition"] = self._safe_text(node.child_by_field_name("condition"), plain)
                comp["increment"] = self._safe_text(node.child_by_field_name("increment"), plain)
            if node.type in ("while_statement", "do_statement"):
                cond = node.child_by_field_name("condition")
                comp["condition"] = self.get_text(cond, plain) if cond else None
            if node.type == "switch_statement":
                value_node = node.child_by_field_name("value")
                comp["value"] = self.get_text(value_node, plain) if value_node else None
            if node.type == "with_statement":
                obj = node.child_by_field_name("object")
                comp["object"] = self.get_text(obj, plain) if obj else None
            if node.type in ("break_statement", "continue_statement"):
                label = node.child_by_field_name("label")
                comp["label"] = self.get_text(label, plain) if label else None
            if node.type == "return_statement":
                value_node = None
                for ch in node.children:
                    if ch.type not in ("return", ";"):
                        value_node = ch
                        break
                comp["value"] = self.get_text(value_node, plain) if value_node else None
            comps.append(comp)

        # Top-level literal expression statements
        if node.type in ("number", "string", "template_string"):
            if node.parent and node.parent.type == "expression_statement" and node.parent.parent and node.parent.parent.type == "program":
                comps.append({
                    "kind": node.type,
                    "module": module_name,
                    "name": self.get_text(node, plain),
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "code": self.get_text(node, plain),
                    "file_path": file_path
                })

        # Assignments / augmented
        if node.type == "assignment_expression":
            comps.append(self._extract_assignment(node, plain, module_name, file_path))
        if node.type == "augmented_assignment_expression":
            comps.append(self._extract_aug_assignment(node, plain, module_name, file_path))

        # Member/subscript/parenthesized (structural nodes)
        if node.type == "member_expression":
            comps.append(self._extract_member(node, plain, module_name, file_path))
        if node.type == "subscript_expression":
            comps.append(self._extract_subscript(node, plain, module_name, file_path))
        if node.type == "parenthesized_expression":
            inner = node.children[1] if len(node.children) > 1 else None
            comps.append({
                "kind": "parenthesized_expression",
                "module": module_name,
                "expression": self.get_text(inner, plain) if inner else None,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "code": self.get_text(node, plain),
                "file_path": file_path
            })

        # New / await / yield / ternary / sequence
        if node.type == "new_expression":
            ctor = node.child_by_field_name("constructor")
            args = node.child_by_field_name("arguments")
            comps.append({
                "kind": "new_expression",
                "module": module_name,
                "constructor": self._safe_text(ctor, plain),
                "arguments": self._safe_text(args, plain),
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "code": self.get_text(node, plain),
                "file_path": file_path
            })
        if node.type == "await_expression":
            comps.append(self._simple(node, plain, module_name, file_path, "await_expression"))
        if node.type == "yield_expression":
            comps.append(self._simple(node, plain, module_name, file_path, "yield_expression"))
        if node.type == "ternary_expression":
            comps.append(self._extract_ternary(node, plain, module_name, file_path))
        if node.type == "sequence_expression":
            exprs = [self.get_text(ch, plain) for ch in node.children if ch.type != ","]
            comps.append({
                "kind": "sequence_expression",
                "module": module_name,
                "expressions": exprs,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "code": self.get_text(node, plain),
                "file_path": file_path
            })

        # Recurse
        for child in node.children:
            comps.extend(self._walk_node(child, plain, file_path, module_name, root_folder))

        return comps

    # ------------- Extract helpers -------------

    def _safe_text(self, node, plain: str) -> Optional[str]:
        if node is None:
            return None
        return self.get_text(node, plain)

    def _simple(self, node, plain, module_name, file_path, kind):
        return {
            "kind": kind,
            "module": module_name,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": self.get_text(node, plain),
            "file_path": file_path
        }

    def _extract_function_like(self, node, plain, module_name, file_path, is_generator=False) -> Dict[str, Any]:
        name_node = node.child_by_field_name("name")
        name = self._safe_text(name_node, plain) or "<anon>"
        params_node = node.child_by_field_name("parameters")
        params = self._safe_text(params_node, plain) or "()"
        body_node = node.child_by_field_name("body")
        calls = self._extract_calls(body_node, plain, module_name, class_ctx=None, bases=None) if body_node else []
        return {
            "kind": "generator_function" if is_generator else "function",
            "module": module_name,
            "name": name,
            "parameters": params,
            "function_calls": calls,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": self.get_text(node, plain),
            "file_path": file_path
        }

    def _extract_class(self, node, plain, module_name, file_path) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        name_node = node.child_by_field_name("name")
        name = self._safe_text(name_node, plain) or "<anon>"

        bases: List[str] = []
        super_node = node.child_by_field_name("superclass")
        if super_node:
            raw = self.get_text(super_node, plain).strip()
            m = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*", raw)
            if m:
                bases.append(m.group(0))
        else:
            # Fallback: parse header before the first '{'
            header = self.get_text(node, plain).split("{", 1)[0]
            m = re.search(r"\bextends\s+([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)?)", header)
            if m:
                bases.append(m.group(1))

        out.append({
            "kind": "class",
            "module": module_name,
            "name": name,
            "bases": bases,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": self.get_text(node, plain),
            "file_path": file_path
        })

        body = node.child_by_field_name("body")
        if body:
            for m in body.children:
                if m.type == "method_definition":
                    method_name_node = m.child_by_field_name("name")
                    method_name = self._safe_text(method_name_node, plain) or "<anon>"
                    params_node = m.child_by_field_name("parameters")
                    params = self._safe_text(params_node, plain) or "()"
                    body_node = m.child_by_field_name("body")
                    calls = self._extract_calls(body_node, plain, module_name, class_ctx=name, bases=bases) if body_node else []
                    out.append({
                        "kind": "method" if method_name != "constructor" else "constructor",
                        "module": module_name,
                        "class": name,
                        "name": method_name,
                        "parameters": params,
                        "function_calls": calls,
                        "start_line": m.start_point[0] + 1,
                        "end_line": m.end_point[0] + 1,
                        "code": self.get_text(m, plain),
                        "file_path": file_path
                    })

        return out

    def _extract_variables(self, node, plain, module_name, file_path) -> List[Dict[str, Any]]:
        """
        Emit variables AND (FIX) emit a component for function/class
        expressions bound to a variable name.
        """
        comps: List[Dict[str, Any]] = []
        kind = "var" if node.type == "variable_declaration" else "let_or_const"
        for d in node.named_children:
            if d.type == "variable_declarator":
                name_node = d.child_by_field_name("name")
                name = self._safe_text(name_node, plain)
                value_node = d.child_by_field_name("value")

                # Function/class expressions become proper components
                if value_node and value_node.type in ("function_expression", "generator_function", "class"):
                    if value_node.type == "class":
                        # class expression under variable
                        if value_node.type == "class":
                            bases = []
                            super_node = value_node.child_by_field_name("superclass")
                            if super_node:
                                raw = self.get_text(super_node, plain).strip()
                                m = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*", raw)
                                if m:
                                    bases.append(m.group(0))
                            else:
                                header = self.get_text(value_node, plain).split("{", 1)[0]
                                m = re.search(r"\bextends\s+([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)?)", header)
                                if m:
                                    bases.append(m.group(1))
                        comps.append({
                            "kind": "class",
                            "module": module_name,
                            "name": name,
                            "bases": bases,
                            "start_line": value_node.start_point[0] + 1,
                            "end_line": value_node.end_point[0] + 1,
                            "code": self.get_text(value_node, plain),
                            "file_path": file_path
                        })
                    else:
                        # function / generator function expression
                        params_node = value_node.child_by_field_name("parameters")
                        params = self._safe_text(params_node, plain) or "()"
                        body_node = value_node.child_by_field_name("body")
                        calls = self._extract_calls(body_node, plain, module_name, class_ctx=None, bases=None) if body_node else []
                        comps.append({
                            "kind": "generator_function" if value_node.type == "generator_function" else "function",
                            "module": module_name,
                            "name": name,
                            "parameters": params,
                            "function_calls": calls,
                            "start_line": value_node.start_point[0] + 1,
                            "end_line": value_node.end_point[0] + 1,
                            "code": self.get_text(value_node, plain),
                            "file_path": file_path
                        })
                    # optionally also emit the variable entry (kept for completeness)
                    comps.append({
                        "kind": "variable",
                        "storage": kind,
                        "module": module_name,
                        "name": name,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "code": self.get_text(node, plain),
                        "file_path": file_path
                    })
                    continue

                # Plain variables
                comps.append({
                    "kind": "variable",
                    "storage": kind,
                    "module": module_name,
                    "name": name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "code": self.get_text(node, plain),
                    "file_path": file_path
                })
        return comps

    def _extract_import(self, node, plain, module_name, file_path) -> Dict[str, Any]:
        text = self.get_text(node, plain).strip()
        src_node = node.child_by_field_name("source")
        src_raw = self._safe_text(src_node, plain)
        source = None
        if src_raw:
            source = src_raw.strip()
            if (source.startswith("'") and source.endswith("'")) or (source.startswith('"') and source.endswith('"')):
                source = source[1:-1]

        details = {
            "default": None,
            "named": [],          # list of {"exported": "...", "local": "..."}
            "namespace": None,    # alias for *
            "side_effect": False
        }

        # Named/default/namespace import parsing
        m_named = re.search(r"import\s*{([^}]+)}\s*from\s*['\"][^'\"]+['\"]", text)
        m_default = re.search(r"import\s+([A-Za-z0-9_$]+)\s*(?:,|from)\s*['\"][^'\"]+['\"]", text)
        m_namespace = re.search(r"import\s+\*\s+as\s+([A-Za-z0-9_$]+)\s*from\s*['\"][^'\"]+['\"]", text)
        m_side = re.match(r"^\s*import\s+['\"][^'\"]+['\"]\s*;?\s*$", text)

        if m_named:
            raw = m_named.group(1)
            names = [x.strip() for x in raw.split(",") if x.strip()]
            for n in names:
                if " as " in n:
                    exported, local = [p.strip() for p in n.split(" as ")]
                else:
                    exported, local = n, n
                details["named"].append({"exported": exported, "local": local})

        if m_namespace:
            details["namespace"] = m_namespace.group(1)

        if m_default and not m_namespace:
            details["default"] = m_default.group(1)

        if m_side and not any([details["default"], details["named"], details["namespace"]]):
            details["side_effect"] = True

        return {
            "kind": "import",
            "module": module_name,
            "source": source,
            "details": details,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": text,
            "file_path": file_path
        }


    def _extract_export(self, node, plain, module_name, file_path) -> List[Dict[str, Any]]:
        """
        Emit real components for 'export' wrappers (functions/classes/variables),
        and also return a small 'export' meta item describing the export.
        This fixes the 'export default function foo(){}' showing up as just 'export'.
        """
        text = self.get_text(node, plain).strip()
        out: List[Dict[str, Any]] = []

        # 1) If this export directly wraps a declaration, emit the declaration(s)
        #    as normal components so they appear as 'function'/'class'/etc.
        for ch in node.children:
            if ch.type in ("function_declaration", "generator_function_declaration"):
                out.append(self._extract_function_like(
                    ch, plain, module_name, file_path, is_generator=("generator" in ch.type)
                ))
            elif ch.type == "class_declaration":
                out.extend(self._extract_class(ch, plain, module_name, file_path))
            elif ch.type in ("variable_declaration", "lexical_declaration"):
                out.extend(self._extract_variables(ch, plain, module_name, file_path))

        # 2) Build a compact export meta record (covers re-exports & default/named)
        #    (kept for downstream tooling that reads export info)
        m_star = re.search(r"export\s+\*\s+from\s+['\"]([^'\"]+)['\"]", text)
        if m_star:
            out.append({
                "kind": "export",
                "module": module_name,
                "name": "*",
                "reexport": True,
                "source": m_star.group(1),
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "code": text,
                "file_path": file_path
            })
            return out

        m_named = re.search(r"export\s*{([^}]+)}\s*(?:from\s+['\"]([^'\"]+)['\"])?", text)
        if m_named:
            raw = m_named.group(1)
            src = m_named.group(2)
            names = [x.strip() for x in raw.split(",") if x.strip()]
            for n in names:
                if " as " in n:
                    exported, alias = [p.strip() for p in n.split(" as ")]
                else:
                    exported, alias = n, n
                out.append({
                    "kind": "export",
                    "module": module_name,
                    "name": alias,           # local export name
                    "exported": exported,    # original symbol name
                    "reexport": bool(src),
                    "source": src,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "code": text,
                    "file_path": file_path
                })
            return out

        # default export (try to capture the identifier if present)
        if re.search(r"export\s+default\s+", text):
            m_id = re.search(r"export\s+default\s+([A-Za-z0-9_$]+)", text)
            name = m_id.group(1) if m_id else "default"
            out.append({
                "kind": "export",
                "module": module_name,
                "name": name,        # will be the identifier if there is one (e.g., 'type_func'), else 'default'
                "default": True,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "code": text,
                "file_path": file_path
            })
            return out

        # generic/fallback export meta
        out.append({
            "kind": "export",
            "module": module_name,
            "name": None,
            "default": False,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": text,
            "file_path": file_path
        })
        return out


    def _extract_assignment(self, node, plain, module_name, file_path) -> Dict[str, Any]:
        left = self._safe_text(node.child_by_field_name("left"), plain)
        right = self._safe_text(node.child_by_field_name("right"), plain)
        return {
            "kind": "assignment_expression",
            "module": module_name,
            "left": left,
            "right": right,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": self.get_text(node, plain),
            "file_path": file_path
        }

    def _extract_aug_assignment(self, node, plain, module_name, file_path) -> Dict[str, Any]:
        left = self._safe_text(node.child_by_field_name("left"), plain)
        op = self._safe_text(node.child_by_field_name("operator"), plain)
        right = self._safe_text(node.child_by_field_name("right"), plain)
        return {
            "kind": "augmented_assignment_expression",
            "module": module_name,
            "left": left,
            "operator": op,
            "right": right,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": self.get_text(node, plain),
            "file_path": file_path
        }

    def _extract_member(self, node, plain, module_name, file_path) -> Dict[str, Any]:
        obj = self._safe_text(node.child_by_field_name("object"), plain)
        prop = self._safe_text(node.child_by_field_name("property"), plain)
        return {
            "kind": "member_expression",
            "module": module_name,
            "object": obj,
            "property": prop,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": self.get_text(node, plain),
            "file_path": file_path
        }

    def _extract_subscript(self, node, plain, module_name, file_path) -> Dict[str, Any]:
        obj = self._safe_text(node.child_by_field_name("object"), plain)
        idx = self._safe_text(node.child_by_field_name("index"), plain)
        return {
            "kind": "subscript_expression",
            "module": module_name,
            "object": obj,
            "index": idx,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": self.get_text(node, plain),
            "file_path": file_path
        }

    def _extract_ternary(self, node, plain, module_name, file_path) -> Dict[str, Any]:
        condition = self._safe_text(node.child_by_field_name("condition"), plain)
        consequence = self._safe_text(node.child_by_field_name("consequence"), plain)
        alternative = self._safe_text(node.child_by_field_name("alternative"), plain)
        return {
            "kind": "ternary_expression",
            "module": module_name,
            "condition": condition,
            "consequence": consequence,
            "alternative": alternative,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "code": self.get_text(node, plain),
            "file_path": file_path
        }

    # ------------- Call extraction -------------

    def _extract_calls(self, node, plain, module_name: str, class_ctx: Optional[str], bases: Optional[List[str]]) -> List[Dict[str, Any]]:
        """
        Recursively collect call expressions as dictionaries:
          - handles identifier calls, member calls, and (fix) super()
          - attaches best-effort local resolution hint
        """
        calls: List[Dict[str, Any]] = []
        if not node:
            return calls

        def visit(n):
            if n.type == "call_expression":
                fn = n.child_by_field_name("function")
                args_node = n.child_by_field_name("arguments")
                args: List[str] = []
                if args_node:
                    for a in args_node.children:
                        if a.type != ",":
                            args.append(self.get_text(a, plain))

                rec = None
                prop = None
                func_name = None
                resolved_hint = None

                if fn:
                    if fn.type == "member_expression":
                        obj_node = fn.child_by_field_name("object")
                        prop_node = fn.child_by_field_name("property")
                        rec = self._safe_text(obj_node, plain)
                        prop = self._safe_text(prop_node, plain)
                        func_name = f"{rec}.{prop}" if rec and prop else self.get_text(fn, plain)

                        if rec == "this" and class_ctx and prop:
                            resolved_hint = f"{module_name}::{class_ctx}::{prop}"
                        elif rec == "super" and bases:
                            base0 = bases[0] if bases else "(super_class)"
                            resolved_hint = f"{module_name}::{base0}.{prop}"
                        else:
                            if rec and re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", rec):
                                resolved_hint = f"{module_name}::{rec}.{prop}"

                    elif fn.type == "identifier":
                        func_name = self.get_text(fn, plain)
                        # FIX: super()
                        if func_name == "super" and bases:
                            resolved_hint = f"{module_name}::{bases[0]}.constructor"
                        else:
                            resolved_hint = f"{module_name}::{func_name}"

                    else:
                        func_name = self.get_text(fn, plain)

                calls.append({
                    "function": func_name,
                    "arguments": "(" + ", ".join(args) + ")",
                    "code": self.get_text(n, plain),
                    "receiver": rec,
                    "property": prop,
                    "resolved_hint": resolved_hint
                })

                # Recurse into args too (calls inside args)
                if args_node:
                    for ch in args_node.children:
                        visit(ch)

            for ch in getattr(n, "children", []):
                visit(ch)

        visit(node)
        return calls
