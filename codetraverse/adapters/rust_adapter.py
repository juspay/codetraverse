import re
from collections import defaultdict
from tqdm import tqdm


def extract_rust_id(comp):
    name_part = comp.get("name") or "<unnamed>"
    module_part = None
    if comp.get("module_name"):
        module_part = comp.get("module_name")
    else:
        module_part = comp.get("module_path") or "<anonymous_module>"
    last_module_segment = module_part.split("::")[-1]
    return f"{last_module_segment}::{name_part}"


def build_module_path_for_component(comp, current_module_stack=[]):
    if comp.get("resolved_module_path"):
        return comp["resolved_module_path"]
    name = comp.get("name", "")
    if current_module_stack:
        return "::".join(current_module_stack + [name])
    else:
        return name


def adapt_rust_components(raw_components: list, quiet: bool = True) -> dict:
    nodes = {}
    edges = []
    all_components = []
    component_queue = list(raw_components)
    module_stack = []

    def process_component_tree(comps, current_module_path=[]):
        for comp in comps:
            comp_module_path = current_module_path.copy()
            if comp.get("type") == "mod_item":
                comp_module_path.append(comp.get("name", ""))
            comp["current_module_path"] = comp_module_path
            children = comp.pop("children", [])
            if children:
                process_component_tree(children, comp_module_path)
            all_components.append(comp)

    process_component_tree(raw_components)
    name_to_fq_ids = defaultdict(list)
    for comp in all_components:
        comp_type = comp.get("type")
        name = comp.get("name")
        if comp_type in {
            "function_item",
            "struct_item",
            "enum_item",
            "trait_item",
            "impl_item",
            "mod_item",
        }:
            if comp.get("current_module_path"):
                module_path = "::".join(comp["current_module_path"])
                if module_path:
                    fq_id = f"{module_path}::{name}"
                else:
                    fq_id = name
            else:
                fq_id = name
            comp["fq_id"] = fq_id
            if name:
                name_to_fq_ids[name].append(fq_id)
    for comp in tqdm(
        all_components, total=len(all_components), desc="Adapting Rust components"
    ):
        comp_type = comp.get("type")
        if comp_type in {
            "function_item",
            "struct_item",
            "enum_item",
            "trait_item",
            "impl_item",
            "mod_item",
        }:
            fq_id = comp.get("fq_id")
            if fq_id:
                nodes[fq_id] = {
                    "id": fq_id,
                    "category": comp_type,
                    "name": comp.get("name"),
                    "file_path": comp.get("file_path"),
                    "start": comp.get("span", {}).get("start_line", 0),
                    "end": comp.get("span", {}).get("end_line", 0),
                }
        source_id = comp.get("fq_id") or comp.get("name", "unknown")
        for call in comp.get("function_calls", []):
            call_name = call.get("name")
            resolved_module = call.get("module_name")
            if resolved_module and resolved_module != call_name:
                target_id = resolved_module
            else:
                target_id = call_name
            if target_id:
                edges.append({"from": source_id, "to": target_id, "relation": "calls"})
        for call in comp.get("method_calls", []):
            method_name = call.get("method")
            resolved_module = call.get("module_name")
            if resolved_module:
                target_id = resolved_module
            else:
                receiver = call.get("receiver", "")
                target_id = f"{receiver}::{method_name}" if receiver else method_name
            if target_id:
                edges.append({"from": source_id, "to": target_id, "relation": "calls"})
        for call in comp.get("macro_calls", []):
            macro_name = call.get("name")
            resolved_module = call.get("module_name")
            target_id = resolved_module if resolved_module else macro_name
            if target_id:
                edges.append({"from": source_id, "to": target_id, "relation": "calls"})
        if comp_type == "use_declaration":
            for import_path in comp.get("imports", []):
                edges.append(
                    {"from": source_id, "to": import_path, "relation": "imports"}
                )
        for type_info in comp.get("types_used", []):
            if isinstance(type_info, dict):
                type_name = type_info.get("name")
                resolved_type = type_info.get("module_name")
                target_id = resolved_type if resolved_type else type_name
            else:
                target_id = str(type_info)
            if target_id:
                edges.append(
                    {"from": source_id, "to": target_id, "relation": "uses_type"}
                )
    final_nodes = list(nodes.values())
    seen_ids = set(nodes.keys())
    for edge in edges:
        for endpoint_key in ("from", "to"):
            endpoint_id = edge[endpoint_key]
            if endpoint_id not in seen_ids:
                category = "external_reference"
                if "::" in endpoint_id:
                    if edge["relation"] == "calls":
                        category = "external_function"
                    elif edge["relation"] == "uses_type":
                        category = "external_type"
                    elif edge["relation"] == "imports":
                        category = "external_module"
                simple_name = endpoint_id.split("::")[-1]
                final_nodes.append(
                    {"id": endpoint_id, "category": category, "name": simple_name}
                )
                seen_ids.add(endpoint_id)
    if not quiet:
        print(f"Created {len(final_nodes)} nodes and {len(edges)} edges.")
    return {"nodes": final_nodes, "edges": edges}
