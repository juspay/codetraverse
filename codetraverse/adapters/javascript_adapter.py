# javascript_adaptor.py
import os
import re
from typing import Dict, Any, List, Optional, Tuple, Set

JS_EXTS = {".js", ".mjs", ".cjs", ".jsx"}

# ---------- basic path helpers ----------

def norm(p: str) -> str:
    return p.replace("\\", "/")

def ensure_js_candidate(path_no_ext: str) -> str:
    """Append .js only if there isn't already a JS-like extension."""
    base, ext = os.path.splitext(path_no_ext)
    if ext in JS_EXTS:
        return norm(path_no_ext)
    return norm(path_no_ext + ".js")

def resolve_relative(from_module: str, spec: str) -> str:
    """
    Resolve './x' '../y' against a repo-prefixed 'from_module' (like comp['module']).
    Bare specs are returned as-is.
    """
    base_dir = os.path.dirname(from_module)
    combined = os.path.normpath(os.path.join(base_dir, spec))
    return norm(combined)

def resolve_symbol_in_imports(
    caller_module: str,
    sym: str,
    import_map_: Dict[str, Dict[str, Tuple[str, str]]],
    export_index_: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """
    Map a local symbol (e.g., 'Greeter' or 'NS.Greeter') to a fully-qualified id:
      - returns '<target_module>::<exported>' (named/default; default rewritten to declared name if known)
      - returns '<target_module>::<prop>' for namespace imports (NS.Prop)
      - falls back to same-module reference.
    """
    imap = import_map_.get(caller_module, {})

    # Namespace import: NS.Greeter
    if "." in sym:
        recv, prop = sym.split(".", 1)
        if recv in imap:
            tgt_mod, exported = imap[recv]
            # namespace import ('*') → use the property name as the symbol
            return f"{tgt_mod}::{prop}"

    # Named/default import: Greeter
    if sym in imap:
        tgt_mod, exported = imap[sym]
        if exported == "default":
            declared = (export_index_.get(tgt_mod, {}) or {}).get("default")
            to_name = declared or "default"
        else:
            to_name = exported
        return f"{tgt_mod}::{to_name}"

    # Relative (rare): './Greeter'
    if sym.startswith("./") or sym.startswith("../"):
        tgt_mod = ensure_js_candidate(resolve_relative(caller_module, sym))
        return f"{tgt_mod}::{os.path.basename(sym)}"

    # Fallback: same file
    return f"{caller_module}::{sym}"


# ---------- node id (simple & stable) ----------

def make_node_id(comp: Dict[str, Any]) -> Optional[str]:
    """
    - methods/ctors/fields: module::Class::method
    - everything named:      module::name
    - literals are skipped as nodes
    """
    kind = comp.get("kind")
    if kind in {"number", "string", "template_string"}:
        return None

    module = comp.get("file_path") or comp.get("module") or os.environ.get("CURRENT_FILE", "unknown")

    if kind in ("method", "constructor", "field") and comp.get("class") and comp.get("name"):
        # Class.member form (keeps IDs consistent with your TS adaptor style)
        return f"{module}::{comp['class']}::{comp['name']}"

    if comp.get("name"):
        return f"{module}::{comp['name']}"

    if comp.get("id"):
        return comp["id"]

    if kind:
        return f"{module}::{kind}"

    return None

# ---------- adaptor ----------

def adapt_javascript_components(raw_components: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Input: list of components from the JS extractor.
    Output: { "nodes": [...], "edges": [...] }.
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    existing_nodes: Set[str] = set()

    if raw_components:
        first = raw_components[0]
        os.environ["ROOT_DIR"] = first.get("root_folder", "") or os.environ.get("ROOT_DIR", "")
        os.environ["CURRENT_FILE"] = first.get("file_path", "") or os.environ.get("CURRENT_FILE", "")

    # ---------- import map ----------
    # { module_path : { local_name : (resolved_target_module, exported_name|*|default) } }
    import_map: Dict[str, Dict[str, Tuple[str, str]]] = {}

    for comp in raw_components:
        if comp.get("kind") != "import":
            continue

        module = comp.get("module") or comp.get("file_path")
        stmt = comp.get("code", "")
        if not module:
            continue

        if module not in import_map:
            import_map[module] = {}

        # named imports
        m = re.match(r"\s*import\s*{([^}]+)}\s*from\s*['\"](.+?)['\"]", stmt)
        if m:
            names, src = m.groups()
            src_rel = resolve_relative(module, src) if src.startswith(".") else src
            src_path = ensure_js_candidate(src_rel)
            for name in [x.strip() for x in names.split(",") if x.strip()]:
                if " as " in name:
                    orig, alias = [n.strip() for n in name.split(" as ")]
                    import_map[module][alias] = (src_path, orig)
                else:
                    import_map[module][name] = (src_path, name)
            continue

        # default import
        m = re.match(r"\s*import\s+([A-Za-z0-9_$]+)\s*from\s*['\"](.+?)['\"]", stmt)
        if m:
            local, src = m.groups()
            src_rel = resolve_relative(module, src) if src.startswith(".") else src
            src_path = ensure_js_candidate(src_rel)
            import_map[module][local] = (src_path, "default")
            continue

        # namespace import
        m = re.match(r"\s*import\s+\*\s+as\s+([A-Za-z0-9_$]+)\s*from\s*['\"](.+?)['\"]", stmt)
        if m:
            ns, src = m.groups()
            src_rel = resolve_relative(module, src) if src.startswith(".") else src
            src_path = ensure_js_candidate(src_rel)
            import_map[module][ns] = (src_path, "*")

    # ---------- export index ----------
    # module_path -> {"default": <declared_name or None>, "named": set([...])}
    export_index: Dict[str, Dict[str, Any]] = {}
    for comp in raw_components:
        if comp.get("kind") != "export":
            continue
        mod = comp.get("module") or comp.get("file_path")
        if not mod:
            continue
        info = export_index.setdefault(mod, {"default": None, "named": set()})
        # named exports
        name = comp.get("name")
        if comp.get("default"):
            # prefer a real declared name if the extractor captured it (e.g., "type_func")
            if name and name != "default":
                info["default"] = name
            # else leave as None (will fall back to "default")
        elif name:
            info["named"].add(name)


    # ---------- nodes ----------
    def add_node(comp: Dict[str, Any]):
        node_id = make_node_id(comp)
        if not node_id:
            return
        kind = comp.get("kind")

        # if the id already exists, prefer real declarations over export wrappers
        if node_id in existing_nodes:
            existing = next((n for n in nodes if n["id"] == node_id), None)
            if existing and existing.get("category") == "export" and kind in {"function","generator_function","class","method","constructor"}:
                # replace the export node with the declaration
                nodes[:] = [n for n in nodes if n["id"] != node_id]
                existing_nodes.remove(node_id)
            else:
                return

        node = {
            "id": node_id,
            "category": "namespace" if kind == "namespace" else kind,
            "parameters": comp.get("parameters"),
            "location": {
                "start": comp.get("start_line"),
                "end": comp.get("end_line"),
                "module": comp.get("module"),
            },
            "bases": comp.get("bases") if kind == "class" else None,
        }
        node = {k: v for k, v in node.items() if v is not None}
        nodes.append(node)
        existing_nodes.add(node_id)


    for comp in raw_components:
        add_node(comp)

    # ---------- helper: enclosing callable contexts ----------
    # function / generator_function / method / constructor / arrow_function
    contexts_by_module: Dict[str, List[Tuple[int, int, str]]] = {}
    for comp in raw_components:
        kind = comp.get("kind")
        if kind not in {"function", "generator_function", "method", "constructor", "arrow_function"}:
            continue
        node_id = make_node_id(comp)
        if not node_id:
            continue
        mod = comp.get("module") or comp.get("file_path")
        start, end = comp.get("start_line"), comp.get("end_line")
        if not mod or start is None or end is None:
            continue
        contexts_by_module.setdefault(mod, []).append((start, end, node_id))

    def find_enclosing_context(mod: str, line: int) -> Optional[str]:
        """Pick the *smallest* span that contains the line."""
        best = None
        best_span = None
        for s, e, nid in contexts_by_module.get(mod, []):
            if s is None or e is None:
                continue
            if s <= line <= e:
                span = e - s
                if best is None or span < best_span:
                    best, best_span = nid, span
        return best

    # ---------- class extends (resolved across files) ----------
    for comp in raw_components:
        if comp.get("kind") == "class" and comp.get("bases"):
            frm = make_node_id(comp)
            caller_module = comp.get("module") or comp.get("file_path")
            if not (frm and caller_module):
                continue
            for base in comp["bases"]:
                base = (base or "").strip()
                if not base:
                    continue
                # keep only Identifier(.Identifier)* (e.g., Greeter, NS.Greeter); drop generics or call tails
                m = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*", base)
                if not m:
                    continue
                base_sym = m.group(0)
                to_id = resolve_symbol_in_imports(caller_module, base_sym, import_map, export_index)
                if to_id and frm != to_id:
                    edges.append({"from": frm, "to": to_id, "relation": "extends"})


    # ---------- call edges (identifier/member) ----------
    def resolve_call_target(caller_module: str, call: Dict[str, Any], import_map_: Dict[str, Dict[str, Tuple[str, str]]], export_index_: Dict[str, Dict[str, str]]) -> Optional[str]:
        recv = call.get("receiver")
        prop = call.get("property")
        fn   = call.get("function")
        hint = call.get("resolved_hint") or call.get("resolved_callee")
        imap = import_map_.get(caller_module, {})

        # Namespace: ns.foo()
        if recv and recv in imap:
            tgt_mod, exported = imap[recv]
            if exported == "*":
                return f"{tgt_mod}::{prop}" if prop else None
            return f"{tgt_mod}::{prop or exported}"

        # Bare identifier imported: greet_user()
        if fn and fn in imap:
            tgt_mod, exported = imap[fn]
            if exported == "default":
                # prefer the declared default name if we know it
                declared = (export_index_.get(tgt_mod, {}) or {}).get("default")
                return f"{tgt_mod}::{declared or 'default'}"
            return f"{tgt_mod}::{exported}"

        # Relative hint "./x::sym"
        if hint and (hint.startswith("./") or hint.startswith("../")):
            parts = hint.split("::", 1)
            if len(parts) == 2:
                rel_file, sym = parts
                abs_file = resolve_relative(caller_module, rel_file)
                return f"{ensure_js_candidate(abs_file)}::{sym}"
            return ensure_js_candidate(resolve_relative(caller_module, hint))

        # Keep other hints (already absolute to a module) or unresolved
        return hint

    for comp in raw_components:
        frm = make_node_id(comp)
        if not frm:
            continue
        caller_module = comp.get("module") or comp.get("file_path")
        for call in comp.get("function_calls", []) or []:
            tgt = resolve_call_target(caller_module, call, import_map, export_index)
            if tgt and frm != tgt:
                edges.append({"from": frm, "to": tgt, "relation": "calls"})

    # ---------- NEW: instantiation edges from `new ...` ----------
    # Creates:
    #   context_function → target_class        (relation = "instantiates")
    #   context_function → target_class.ctor  (relation = "calls", if ctor node exists)
    for comp in raw_components:
        if comp.get("kind") != "new_expression":
            continue
        caller_module = comp.get("module") or comp.get("file_path")
        line = comp.get("start_line")
        if not caller_module or line is None:
            continue

        caller_id = find_enclosing_context(caller_module, line)
        if not caller_id:
            continue  # skip top-level news for now

        ctor = (comp.get("constructor") or "").strip()
        if not ctor:
            continue

        # Resolve constructor symbol to a module + class name
        tgt_module = None
        cls_name = None

        imap = import_map.get(caller_module, {})
        if "." in ctor:
            # e.g., NS.Person
            recv, cls_name = ctor.split(".", 1)
            if recv in imap:
                tgt_module, exported = imap[recv]
                # namespace import -> '*'
                # even if someone did "import * as NS from './x.js'", we just use cls_name
                if exported != "*":
                    # odd case, but fall back to exported if not namespace
                    cls_name = cls_name or exported
        else:
            # e.g., Person
            if ctor in imap:
                tgt_module, exported = imap[ctor]
                if exported == "default":
                    declared = (export_index.get(tgt_module, {}) or {}).get("default")
                    cls_name = declared or "default"
                else:
                    cls_name = exported
            else:
                # local class in same module
                tgt_module, cls_name = caller_module, ctor

        if not tgt_module or not cls_name:
            continue

        class_id = f"{tgt_module}::{cls_name}"
        ctor_id  = f"{tgt_module}::{cls_name}::constructor"

        edges.append({"from": caller_id, "to": class_id, "relation": "instantiates"})
        if ctor_id in (n["id"] for n in nodes):
            edges.append({"from": caller_id, "to": ctor_id, "relation": "calls"})

    # ---------- file deps (fdeps) ----------
    for comp in raw_components:
        if comp.get("kind") != "import":
            continue
        mod = comp.get("module") or comp.get("file_path")
        stmt = comp.get("code", "")
        if not (mod and stmt):
            continue
        m = re.search(r"from\s*['\"](.+?)['\"]", stmt)
        if not m:
            continue
        src = m.group(1)
        if src.startswith("."):
            target = ensure_js_candidate(resolve_relative(mod, src))
        else:
            vendor_root = os.environ.get("VENDOR_ROOT", "vendor")
            target = ensure_js_candidate(norm(os.path.join(vendor_root, src)))
        if mod != target:
            edges.append({"from": mod, "to": target, "relation": "fdeps"})

    # ---------- class → member containment ----------
    for comp in raw_components:
        if comp.get("kind") in {"method", "constructor", "field"} and comp.get("class"):
            class_id  = f"{comp['module']}::{comp['class']}"
            member_id = make_node_id(comp)
            if class_id and member_id and class_id != member_id:
                # edges.append({"from": class_id, "to": member_id, "relation": "member"})
                edges.append({"from": class_id, "to": member_id, "relation": "calls"})


    # keep only well-formed edges
    edges = [e for e in edges if e.get("from") and e.get("to")]
    return {"nodes": nodes, "edges": edges}
