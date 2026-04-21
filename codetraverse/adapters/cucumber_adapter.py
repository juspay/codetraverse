# codetraverse/adapters/cucumber_adapter.py

import os


def infer_project_root(components):
    paths = [os.path.abspath(comp["module"]) for comp in components if comp.get("module")]
    return os.path.commonpath(paths) if paths else None


def make_node_id(comp):
    module = comp.get("file_path") or comp.get("module") or os.environ.get("CURRENT_FILE", "<unknown>")
    kind = comp.get("kind")
    name = comp.get("name", "unnamed")
    
    return f"{module}::{name}"


def adapt_cucumber_components(raw_components):
    nodes = []
    edges = []

    if raw_components:
        pr = infer_project_root(raw_components)
        os.environ["ROOT_DIR"] = pr
        os.environ["CURRENT_FILE"] = raw_components[0]["module"]

    existing = set()
    
    # Group components by file
    components_by_file = {}
    for comp in raw_components:
        fpath = comp.get("file_path", "")
        components_by_file.setdefault(fpath, []).append(comp)

    # First, add Feature nodes
    features = [c for c in raw_components if c.get("kind") == "feature"]
    for feat in features:
        nid = make_node_id(feat)
        if nid in existing:
            continue
        existing.add(nid)

        node = {
            "id": nid,
            "category": "feature",
            "description": feat.get("description"),
            "tags": feat.get("tags"),
            "location": {
                "start": feat.get("start_line"),
                "end": feat.get("end_line"),
                "module": feat.get("module")
            },
        }
        node = {k: v for k, v in node.items() if v is not None}
        nodes.append(node)

    # Background nodes
    backgrounds = [c for c in raw_components if c.get("kind") == "background"]
    for bg in backgrounds:
        nid = make_node_id(bg)
        if nid in existing:
            continue
        existing.add(nid)

        node = {
            "id": nid,
            "category": "background",
            "description": bg.get("description"),
            "steps": bg.get("steps"),
            "location": {
                "start": bg.get("start_line"),
                "end": bg.get("end_line"),
                "module": bg.get("module")
            },
        }
        node = {k: v for k, v in node.items() if v is not None}
        nodes.append(node)

    # Scenario and Scenario Outline nodes
    scenarios = [c for c in raw_components if c.get("kind") in ("scenario", "scenario_outline")]
    for scen in scenarios:
        nid = make_node_id(scen)
        if nid in existing:
            continue
        existing.add(nid)

        node = {
            "id": nid,
            "category": scen.get("kind"),
            "tags": scen.get("tags"),
            "steps": scen.get("steps"),
            "examples": scen.get("examples"),
            "location": {
                "start": scen.get("start_line"),
                "end": scen.get("end_line"),
                "module": scen.get("module")
            },
        }
        node = {k: v for k, v in node.items() if v is not None}
        nodes.append(node)

    # Edge: Feature contains Scenario/Background
    for feat in features:
        from_id = make_node_id(feat)
        
        # Find scenarios in the same file
        file_path = feat.get("file_path")
        file_scenarios = [c for c in raw_components 
                         if c.get("file_path") == file_path 
                         and c.get("kind") in ("scenario", "scenario_outline")]
        
        for scen in file_scenarios:
            to_id = make_node_id(scen)
            edges.append({"from": from_id, "to": to_id, "relation": "contains"})
        
        # Find backgrounds in the same file
        file_backgrounds = [c for c in raw_components 
                           if c.get("file_path") == file_path 
                           and c.get("kind") == "background"]
        
        for bg in file_backgrounds:
            to_id = make_node_id(bg)
            edges.append({"from": from_id, "to": to_id, "relation": "contains"})

    # Edge: Scenario uses Background
    for scen in scenarios:
        if scen.get("uses_background") and scen.get("background"):
            from_id = make_node_id(scen)
            file_path = scen.get("file_path")
            
            # Find the background in the same file
            bg = next((c for c in raw_components 
                      if c.get("file_path") == file_path 
                      and c.get("kind") == "background"
                      and c.get("name") == scen.get("background")), None)
            
            if bg:
                to_id = make_node_id(bg)
                edges.append({"from": from_id, "to": to_id, "relation": "uses_background"})

    # Filter empty edges
    edges = [e for e in edges if e["from"] and e["to"]]
    
    return {"nodes": nodes, "edges": edges}
