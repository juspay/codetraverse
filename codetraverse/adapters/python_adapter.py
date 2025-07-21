# codetraverse/adapters/python_adapter.py

import os
import re

def infer_project_root(components):
    paths = [os.path.abspath(comp["module"]) for comp in components if comp.get("module")]
    return os.path.commonpath(paths) if paths else None

def make_node_id(comp):
    # module = comp.get("module") or os.environ.get("CURRENT_FILE","<unknown>")
    module = comp.get("file_path") or comp.get("module") or os.environ.get("CURRENT_FILE","<unknown>")
    kind   = comp.get("kind")
    if kind in ("method","async_method") and comp.get("class") and comp.get("name"):
        return f"{module}::{comp['class']}.{comp['name']}"
    elif kind in ("lambda","yield","list_comprehension","set_comprehension", # few fileds are not been used as they are not importnant
                "dict_comprehension","generator_expression"):
        return f"{module}::{kind}.{comp['start_line']}"
    elif comp.get("name"):
        return f"{module}::{comp['name']}"
    # fallback
    return f"{module}::{kind}.{comp.get('start_line')}"

def adapt_python_components(raw_components):
    nodes = []
    edges = []

    if raw_components:
        # os.environ["ROOT_DIR"]     = os.path.dirname(raw_components[0]["module"])
        # infer the common ancestor of all component modules
        pr = infer_project_root(raw_components)
        os.environ["ROOT_DIR"]     = pr
        os.environ["CURRENT_FILE"] = raw_components[0]["module"]

    project_root = infer_project_root(raw_components)

    existing = set()

    # build import map
    import_map = {}
    # for comp in raw_components:
    #     if comp["kind"] == "import" and comp.get("imported") and comp.get("from"):
    #         m = comp["module"]
    #         import_map.setdefault(m,{})[comp["imported"]] = comp["from"]
    for comp in raw_components:
        if comp["kind"] == "import" and comp.get("name") and comp.get("from"):
            mod = comp["file_path"]
            import_map.setdefault(mod,{})[comp["name"]] = comp["from"]

    # nodes
    for comp in raw_components:
        nid = make_node_id(comp)
        if nid in existing:
            continue
        existing.add(nid)

        node = {
            "id":        nid,
            "category":  comp["kind"],
            "decorators": comp.get("decorators"),
            "parameters": comp.get("parameters"),
            "returns":   comp.get("returns"),
            "annotation": comp.get("annotation") or comp.get("annotation"),
            "location": {
                "start":  comp.get("start_line"),
                "end":    comp.get("end_line"),
                "module": comp.get("module")
            },
        }
        # remove nulls
        node = {k:v for k,v in node.items() if v is not None}
        nodes.append(node)

    # inheritance edges
    for comp in raw_components:
        if comp["kind"] == "class" and comp.get("bases"):
            from_id = make_node_id(comp)
            for b in comp["bases"]:
                # to_id = f"{comp['module']}::{b}"
                to_id = f"{comp['file_path']}::{b}"
                edges.append({"from":from_id,"to":to_id,"relation":"extends"})

    # call edges
    for comp in raw_components:
        if comp.get("function_calls"):
            from_id = make_node_id(comp)
            for call in comp["function_calls"]:
                tgt = call.get("resolved_callee")
                if not tgt: continue
                # if imported
                parts = tgt.split("::")
                # if len(parts)==2 and import_map.get(comp["module"],{}).get(parts[1]):
                #     tgt = f"{import_map[comp['module']][parts[1]]}::{parts[1]}"
                if len(parts)==2 and import_map.get(comp["file_path"],{}).get(parts[1]):
                    # always force a .py path here
                    mod = import_map[comp["file_path"]][parts[1]]
                    path = mod.replace(".", "/") + ".py"
                    tgt = f"{path}::{parts[1]}"
                if from_id != tgt:
                    edges.append({"from":from_id,"to":tgt,"relation":"calls"})

    # filter empty
    edges = [e for e in edges if e["from"] and e["to"]]
    return {"nodes":nodes,"edges":edges}
