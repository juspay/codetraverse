from tqdm import tqdm
from collections import defaultdict
import re

def adapt_haskell_components(raw_components):
    nodes = []
    edges = []
    node_ids = set()

    all_comps_by_module = defaultdict(list)
    main_modules_by_file = {
        comp['file_path']: comp['name']
        for comp in raw_components if comp.get("kind") == "module_header"
    }

    for comp in raw_components:
        name = comp.get("name")
        file_path = comp.get("file_path")
        if not (name and file_path): continue
        
        comp_module = comp.get("module", main_modules_by_file.get(file_path))
        if not comp_module: continue
            
        comp["module"] = comp_module
        all_comps_by_module[comp_module].append(comp)

    comps_by_file = defaultdict(list)
    for comp in raw_components:
        if comp.get("file_path"):
            comps_by_file[comp.get("file_path")].append(comp)

    for file_path, file_comps in comps_by_file.items():
        import_alias_map = {
            imp['alias']: imp['module']
            for imp in file_comps if imp.get("kind") == "import" and imp.get("alias")
        }
        
        for comp in file_comps:
            kind, name, comp_module = comp.get("kind"), comp.get("name"), comp.get("module")
            if not (kind and name and comp_module): continue
            
            source_id = f"{comp_module}::{name}"
            if source_id not in node_ids:
                node_category = kind
                if kind == "module_header": node_category = "module"
                if kind == "class": node_category = "typeclass"
                
                nodes.append({
                    "id": source_id, "category": node_category, "name": name,
                    "file_path": comp.get("file_path", ""),
                    "location": {"start": comp.get("start_line"),"end": comp.get("end_line")}
                })
                node_ids.add(source_id)

            if kind == "module_header":
                for export in comp.get("exports", []):
                    if export in import_alias_map:
                        alias = export
                        actual_module_names = [imp['module'] for imp in file_comps if imp.get("alias") == alias]

                        for actual_module_name in actual_module_names:
                            for target_comp in all_comps_by_module.get(actual_module_name, []):
                                target_name = target_comp.get("name")
                                if not target_name: continue
                                
                                proxy_id = f"{comp_module}::{target_name}"
                                if proxy_id not in node_ids:
                                    nodes.append({
                                        "id": proxy_id, "category": "reexport", "name": target_name,
                                        "file_path": comp.get("file_path", ""), "location": {}
                                    })
                                    node_ids.add(proxy_id)
                                
                                edges.append({"from": source_id, "to": proxy_id, "relation": "exports"})
                                actual_id = f"{target_comp['module']}::{target_name}"
                                edges.append({"from": proxy_id, "to": actual_id, "relation": "reexport_of"})
                    else:
                        edges.append({"from": source_id, "to": f"{comp_module}::{export}", "relation": "exports"})

            elif kind == "function":
                for call in comp.get("function_calls", []):
                    call_base = call.get("base", call.get("name"))
                    if not call_base: continue
                    target_module = call.get('modules', [comp_module])[0]
                    edges.append({"from": source_id, "to": f"{target_module}::{call_base}", "relation": "calls"})

                for dep in comp.get("type_dependencies", []):
                    dep_mod, _, dep_name = dep.rpartition('.')
                    edges.append({"from": source_id, "to": f"{dep_mod or comp_module}::{dep_name}", "relation": "uses_type"})
            
            elif kind == "instance":
                class_name = comp["name"].split()[0]
                class_id = f"{comp_module}::{class_name}"
                edges.append({"from": source_id, "to": class_id, "relation": "implements"})

    all_node_ids_final = {n['id'] for n in nodes}
    for edge in edges:
        for endpoint in ("from", "to"):
            if edge[endpoint] not in all_node_ids_final:
                nodes.append({"id": edge[endpoint], "category": "external", "name": edge[endpoint].split("::")[-1], "file_path": "external"})
                all_node_ids_final.add(edge[endpoint])
    
    print(f"Adapted {len(nodes)} nodes and {len(edges)} edges")
    return {"nodes": nodes, "edges": edges}