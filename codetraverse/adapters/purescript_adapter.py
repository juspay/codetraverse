# purescript_adapter.py

import os
import re
from collections import defaultdict

def infer_project_root(components):
    """
    Find the common base directory of all PureScript modules.
    """
    paths = [os.path.abspath(comp["file_path"])
             for comp in components if comp.get("file_path")]
    return os.path.commonpath(paths) if paths else None

def make_node_id(comp):
    """
    Build a stable node ID:
      - Prefer the declared PureScript module name.
      - Fallback to the relative file path (drop .purs).
      - Append ::<symbol> if present.
    """
    mod = comp.get("module")
    if mod:
        base = mod
    else:
        fp = comp.get("file_path", "")
        base = fp[:-5] if fp.endswith(".purs") else fp

    name = comp.get("name")
    if name:
        return f"{base}.purs::{name}"
    if comp.get("id"):
        return comp["id"]
    return None

def adapt_purescript_components(raw_components):
    """
    Turn a flat list of PureScript components into a node/edge graph.
    """
    # — initialize environment
    if raw_components:
        os.environ["ROOT_DIR"] = infer_project_root(raw_components) or ""
        # pick first file as “current” for fallback
        os.environ["CURRENT_FILE"] = raw_components[0].get("file_path", "")

    # — group by file for per-file import maps
    comps_by_file = defaultdict(list)
    for c in raw_components:
        if c.get("file_path"):
            comps_by_file[c["file_path"]].append(c)

    # — build import_map[file] = (moduleName, { alias → targetModule })
    file_imports = {}
    for fp, comps in comps_by_file.items():
        # find the module name declared in that file (all import comps share it)
        module_name = None
        for c in comps:
            if c.get("kind") == "import":
                module_name = c["module"]
                break

        alias_map = {}
        for imp in (c for c in comps if c.get("kind") == "import"):
            src_mod = imp["module"]
            code    = imp.get("code", "")

            # 1) parse everything in parentheses: `import M ( a, b, class C, Method(GET) )`
            m = re.search(r'import\s+[\w\.]+\s*\(([^)]+)\)', code)
            if m:
                for item in m.group(1).split(','):
                    tok = item.strip()
                    # class import
                    if tok.startswith('class '):
                        _, cls = tok.split(None,1)
                        alias_map[cls] = src_mod
                    # Method(GET) style
                    elif meth := re.match(r'Method\s*\(\s*([A-Z][A-Z0-9_]*)\s*\)', tok):
                        alias_map[meth.group(1)] = src_mod
                    else:
                        alias_map[tok] = src_mod

            # 2) fallback: if extractor supplied an `imports` dict on the comp
            for name, tgt in imp.get("imports", {}).items():
                alias_map[name] = tgt

        file_imports[fp] = (module_name, alias_map)

    nodes = []
    edges = []
    seen  = set()

    # — 1) Create rich nodes for every component
    for comp in raw_components:
        nid = make_node_id(comp)
        if not nid or nid in seen:
            continue
        seen.add(nid)

        kind = comp.get("kind")
        node = {
            "id":       nid,
            "category": kind,
            "module":   comp.get("module"),
            "signature": comp.get("type_signature"),
            "parameters": comp.get("parameters"),
            "location": {
                "start": comp.get("start_line"),
                "end":   comp.get("end_line"),
                "file":  comp.get("file_path"),
            }
        }

        # kind-specific extras:
        if kind == "type_alias":
            node["type_dependencies"] = comp.get("type_dependencies")
        if kind in ("data_declaration", "newtype"):
            node["constructors"] = comp.get("constructors")
        if kind == "class":
            node["fundeps"] = comp.get("fundeps")           # if you capture those
        if kind == "instance":
            node["implements"] = comp.get("instance_name")
        if kind == "pattern_synonym":
            node["type_signature"] = comp.get("type_signature")

        # drop empties
        node = {k: v for k, v in node.items() if v not in (None, {}, [])}
        nodes.append(node)

    # — 2) Module‐ and symbol‐level import edges
    for fp, (mod, alias_map) in file_imports.items():
        if not mod:
            continue
        for alias, tgt_mod in alias_map.items():
            # module → module
            if mod != tgt_mod:
                edges.append({"from": mod,      "to": tgt_mod,   "relation": "imports"})
            # symbol → symbol
            from_sym = f"{mod}.purs::{alias}"
            to_sym   = f"{tgt_mod}.purs::{alias}"
            if from_sym != to_sym:
                edges.append({"from": from_sym, "to": to_sym,   "relation": "imports"})

    # — 3) Call‐ and type‐dependency edges
    for comp in raw_components:
        src = make_node_id(comp)
        if not src:
            continue
        # calls
        for call in comp.get("function_calls", []):
            tgt = call.get("resolved_callee")
            if tgt and src != tgt:
                edges.append({"from": src, "to": tgt, "relation": "calls"})
        # type dependencies
        for dep in comp.get("type_dependencies", []):
            mod = comp.get("module","")
            tgt = f"{mod}.purs::{dep}"
            if src != tgt:
                edges.append({"from": src, "to": tgt, "relation": "type_dependency"})

    # — 4) Extends / Implements edges
    for comp in raw_components:
        if comp.get("kind") == "class" and comp.get("bases"):
            src = make_node_id(comp)
            for base in comp["bases"]:
                edges.append({
                    "from": src,
                    "to":   f"{comp['module']}.purs::{base}",
                    "relation": "extends"
                })
        if comp.get("kind") == "class_instance":
            src = make_node_id(comp)
            cls = comp.get("instance_name")
            if cls:
                edges.append({
                    "from": src,
                    "to":   f"{comp['module']}.purs::{cls}",
                    "relation": "implements"
                })

    # — 5) (Optional) ‘fdeps’ if you ever emit those
    for comp in raw_components:
        if comp.get("operator") in {"typeof","keyof"} and comp.get("deps"):
            src = comp.get("id")
            for d in comp["deps"]:
                tgt = f"{comp['module']}.purs::{d}" if "::" not in d else d
                if src and src != tgt:
                    edges.append({"from": src, "to": tgt, "relation": "fdeps"})

    # — 6) Class → Method edges
    for comp in raw_components:
        if comp["kind"] == "class" and comp.get("has_methods"):
            class_id = make_node_id(comp)
            for method_id in comp["has_methods"]:
                edges.append({
                    "from":     class_id,
                    "to":       method_id,
                    "relation": "has_method"
                })

    # — filter out any incomplete edges
    edges = [e for e in edges if e.get("from") and e.get("to")]

    return {"nodes": nodes, "edges": edges}
