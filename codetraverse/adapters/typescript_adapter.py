import os
import re

def infer_project_root(components):
    module_paths = [os.path.abspath(comp["module"]) for comp in components if comp.get("module")]
    if module_paths:
        return os.path.commonpath(module_paths)
    return None

def make_node_id(comp):
    ROOT_DIR = os.environ.get("ROOT_DIR", "")
    module = comp.get("file_path")
    # print("siraj module:", module)
    # remove the root directory from the module path
    # if module and ROOT_DIR:
    #     module = os.path.relpath(module, ROOT_DIR).replace("\\", "/")
    # last_dir = os.path.basename(ROOT_DIR)
    # index = module.find(last_dir)
    # if index != -1:
    #     module = module[index:]

    if not module:
        module = os.environ.get("CURRENT_FILE", "unknown")

    if comp.get("kind") in ("method", "field") and comp.get("class") and comp.get("name"):
        return f"{module}::{comp['class']}::{comp['name']}"     # +"siraj_node101"
    if comp.get("kind") == "namespace" and comp.get("name"):
        return f"{module}::{comp['name']}" # only one node for namespace in xyne repo (i.e Google)
    if comp.get("name"):
        return f"{module}::{comp['name']}"    #+"siraj_node303"
    if comp.get("id"):
        return comp["id"]  # +"siraj_node404"
    return None

def adapt_typescript_components(raw_components):
    nodes = []
    edges = []

    if raw_components:
        first = raw_components[0]
        os.environ["ROOT_DIR"] = first.get("root_folder", "")
        os.environ["CURRENT_FILE"] = first.get("file_path", "")

    project_root = infer_project_root(raw_components)
    import_map = {}

    # 1. Build import map
    for comp in raw_components:
        if comp.get("kind") == "import":
            module = comp["module"]
            stmt = comp["code"]
            module_dir = os.path.dirname(module)

            if module not in import_map:
                import_map[module] = {}

            # Named imports
            m = re.match(r"import\s+{([^}]+)}\s+from\s+['\"](.+)['\"]", stmt)
            if m:
                names, src = m.groups()
                src_path = os.path.normpath(os.path.join(module_dir, src + ".ts")).replace("\\", "/")
                for name in names.split(","):
                    name = name.strip()
                    if " as " in name:
                        orig, alias = [n.strip() for n in name.split(" as ")]
                        import_map[module][alias] = (src_path, orig)
                    else:
                        import_map[module][name] = (src_path, name)
                continue

            # Default import
            m = re.match(r"import\s+([a-zA-Z0-9_$]+)\s+from\s+['\"](.+)['\"]", stmt)
            if m:
                name, src = m.groups()
                src_path = os.path.normpath(os.path.join(module_dir, src + ".ts")).replace("\\", "/")
                import_map[module][name] = (src_path, "default")
                continue

            # Namespace
            m = re.match(r"import\s+\*\s+as\s+([a-zA-Z0-9_$]+)\s+from\s+['\"](.+)['\"]", stmt)
            if m:
                ns, src = m.groups()
                src_path = os.path.normpath(os.path.join(module_dir, src + ".ts")).replace("\\", "/")
                import_map[module][ns] = (src_path, "*")
    existing_nodes = set()

    for comp in raw_components:
        kind = comp.get("kind")
        node_id = make_node_id(comp)

        if not node_id or node_id in existing_nodes:
            continue

        category = kind if kind != "namespace" else "namespace"

        node = {
            "id": node_id,
            "category": category,
            "signature": comp.get("type_signature"),
            "type_parameters": comp.get("type_parameters"),
            "type_parameters_structured": comp.get("type_parameters_structured"),
            "utility_type": comp.get("utility_type"),
            "parameters": comp.get("parameters"),
            "decorators": comp.get("decorators"),
            "location": {
                "start": comp.get("start_line"),
                "end": comp.get("end_line"),
                "module": comp.get("module"),
            },
            "value": comp.get("value") if kind == "variable" else None,
            "bases": comp.get("bases") if kind == "class" else None,
            "implements": comp.get("implements") if kind == "class" else None,
            "extends": comp.get("extends") if kind == "interface" else None,
            "members": comp.get("members"),
            "static": comp.get("static"),
            "abstract": comp.get("abstract"),
            "readonly": comp.get("readonly"),
            "override": comp.get("override"),
            "getter": comp.get("getter"),
            "setter": comp.get("setter"),
            "type_param_constraints": comp.get("type_param_constraints"),
            "index_signatures": comp.get("index_signatures"),
        }

        node = {k: v for k, v in node.items() if v is not None}
        nodes.append(node)
        existing_nodes.add(node_id)
        if comp.get("operator") in {"typeof", "keyof"} and comp.get("id"):
            node_id = comp["id"]
            op = comp["operator"]
            if node_id not in existing_nodes:
                nodes.append({
                    "id": node_id,
                    "category": op,
                    "label": f"{op} {comp.get('target')}",
                    "target": comp.get("target"),
                    "deps": comp.get("deps"),
                    "ast_type": comp.get("ast_type"),
                })
                existing_nodes.add(node_id)

        if kind == "type_alias" and comp.get("utility_type"):
            alias_id = make_node_id(comp)
            ut = comp["utility_type"]
            utility_node_id = f"utility::{ut['utility_type']}"

            if utility_node_id not in existing_nodes:
                nodes.append({
                    "id": utility_node_id,
                    "category": "utility_type",
                    "utility_type": ut["utility_type"]
                })
                existing_nodes.add(utility_node_id)

            edges.append({
                "from": alias_id,
                "to": utility_node_id,
                "relation": "utility_type"
            })

            for arg in ut["args"]:
                arg_id = f"{comp['module']}::{arg}" if "::" not in arg else arg
                if arg_id not in existing_nodes:
                    nodes.append({
                        "id": arg_id,
                        "category": "type"
                    })
                    existing_nodes.add(arg_id)
                edges.append({
                    "from": utility_node_id,
                    "to": arg_id,
                    "relation": "utility_argument"
                })


    for comp in raw_components:
        if comp.get("kind") == "class" and comp.get("bases"):
            from_id = make_node_id(comp)
            for base in comp["bases"]:
                to_id = f"{comp['module']}::{base}"
                edges.append({
                    "from": from_id,
                    "to": to_id,
                    "relation": "extends"
                })


    for comp in raw_components:
        if comp.get("kind") == "interface" and comp.get("extends"):
            from_id = make_node_id(comp)
            for base in comp["extends"]:
                to_id = f"{comp['module']}::{base}"
                edges.append({
                    "from": from_id,
                    "to": to_id,
                    "relation": "extends"
                })


    for comp in raw_components:
        if comp.get("kind") == "class" and comp.get("implements"):
            from_id = make_node_id(comp)
            for iface in comp["implements"]:
                to_id = f"{comp['module']}::{iface}"
                edges.append({
                    "from": from_id,
                    "to": to_id,
                    "relation": "implements"
                })


    for comp in raw_components:
        kind = comp.get("kind")
        if kind not in {"function", "method", "variable", "function_call", "arrow_function", "generator_function", "generator_function_declaration"}:
            continue
        if kind == "generator_function_declaration":
            print("siraj kind:", kind)

        from_id = make_node_id(comp)
        if not from_id or not comp.get("function_calls"):
            continue

        # derive caller path from from_id
        caller_module = from_id.split("::", 1)[0]
        caller_dir    = os.path.dirname(caller_module)

        for call in comp.get("function_calls", []):
            target_id = call.get("resolved_callee")
            if not target_id:
                continue

            # # ——— handle TS "@/…" alias imports ———
            # if target_id.startswith("@"):
            #     # strip leading "@/" to get the suffix
            #     alias_suffix = target_id[1:].lstrip("/")
            #     # find all existing nodes ending with that suffix
            #     candidates = [
            #         nid for nid in existing_nodes
            #         if not nid.startswith("@") and nid.endswith(alias_suffix)
            #     ]
            #     if candidates:
            #         # score each by shared path segments with caller_dir
            #         scored = []
            #         for nid in candidates:
            #             cand_module = nid.split("::", 1)[0]
            #             common = os.path.commonpath([caller_dir, cand_module])
            #             segments = common.split(os.sep) if common else []
            #             scored.append((len(segments), nid))
            #         max_score = max(score for score, _ in scored)
            #         best = [nid for score, nid in scored if score == max_score]
            #         for nid in best:
            #             if from_id != nid:
            #                 edges.append({
            #                     "from":     from_id,
            #                     "to":       nid,
            #                     "relation": "calls"
            #                 })
            #     continue  # skip the rest and go to next call

            # ——— handle "./" or "../" relative imports ———
            if target_id.startswith("."):
                parts = target_id.split("::")
                if len(parts) == 2:
                    target_file, target_symbol = parts
                    from_file = caller_module
                    from_dir  = os.path.dirname(from_file)
                    combined = os.path.normpath(
                        os.path.join(from_dir, target_file)
                    ).replace("\\", "/")
                    target_id = f"{combined}::{target_symbol}"

            # ——— emit the edge for non-alias or resolved-relative cases ———
            if from_id != target_id:
                edges.append({
                    "from":     from_id,
                    "to":       target_id,
                    "relation": "calls"
                })



    for comp in raw_components:
        if comp.get("kind") == "type_alias" and comp.get("type_dependencies"):
            from_id = make_node_id(comp)
            for dep in comp["type_dependencies"]:
                to_id = f"{comp['module']}::{dep}"
                if from_id != to_id:
                    edges.append({
                        "from": from_id,
                        "to": to_id,
                        "relation": "type_dependency"
                    })


    for comp in raw_components:
        if comp.get("operator") in {"typeof", "keyof"} and comp.get("deps"):
            from_id = comp["id"]
            for dep in comp["deps"]:
                
                to_id = f"{comp['module']}::{dep}" if "::" not in dep else dep
                if from_id != to_id:
                    edges.append({
                        "from": from_id,
                        "to": to_id,
                        "relation": "fdeps"
                    })

    filtered_edges = [e for e in edges if e["from"] and e["to"]]
    return {
        "nodes": nodes,
        "edges": filtered_edges
    }