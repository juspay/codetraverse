import os
import json
import networkx as nx
from tqdm import tqdm

def load_components(fdep_dir):
    from adapters.rescript_adapter import extract_id

    funcs = {}
    for dirpath, _, files in os.walk(fdep_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            fullpath = os.path.join(dirpath, fn)
            with open(fullpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for comp in data:
                fq = extract_id(comp)
                funcs[fq] = comp
    return funcs

def load_components_without_hash(fdep_dir):
    components = []
    for dirpath, _, files in os.walk(fdep_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            fullpath = os.path.join(dirpath, fn)
            with open(fullpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            components.extend(data)
    return components



def build_graph_from_schema(schema):
    G = nx.DiGraph()

    for node in schema["nodes"]:
        nid = node["id"]
        attrs = {}
        for (k, v) in node.items():
            if k == "id":
                continue
            if v is None:
                attrs[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                attrs[k] = v
            else:
                attrs[k] = json.dumps(v)
        G.add_node(nid, **attrs)

    for edge in schema["edges"]:
        src = edge["from"]
        dst = edge["to"]
        rel = edge.get("relation") or ""
        G.add_edge(src, dst, relation=rel)

    return G
