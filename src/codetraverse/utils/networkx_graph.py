import os
import json
import networkx as nx
from tqdm import tqdm
from codetraverse.adapters.rescript_adapter import extract_id

def load_components(fdep_dir):
    """
    Walk all .json files under fdep_dir, load each array of components,
    then add them into a dict keyed by extract_id(comp) so that each
    component is uniquely identified by "module::name".
    """

    funcs = {}
    args = []

    for dirpath, _, files in os.walk(fdep_dir):
        args.extend([os.path.join(dirpath, fn) for fn in files if fn.endswith(".json")])
    
    for fullpath in tqdm(args, desc="Reading JSONs"):
        with open(fullpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for comp in data:
            fq = extract_id(comp)
            funcs[fq] = comp
    return funcs


def build_graph_from_schema(schema):
    """
    Given the {"nodes": […], "edges": […]} schema returned by our adapter,
    produce a networkx.DiGraph where **no attribute** is ever None.
    All None → "", and non‐primitives get JSON‐dumped.
    """
    G = nx.DiGraph()

    # 1) Add nodes
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
                # lists, dicts, etc. → JSON‐dump as a string
                attrs[k] = json.dumps(v)
        G.add_node(nid, **attrs)

    # 2) Add edges
    for edge in schema["edges"]:
        src = edge["from"]
        dst = edge["to"]
        rel = edge.get("relation") or ""
        G.add_edge(src, dst, relation=rel)

    return G
