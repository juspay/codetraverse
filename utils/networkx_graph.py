import os
import json
import networkx as nx
from tqdm import tqdm

def load_components(fdep_dir):
    funcs = {}
    for dirpath, _, files in os.walk(fdep_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            full = os.path.join(dirpath, fn)
            with open(full, "r", encoding="utf-8") as f:
                data = json.load(f)
            for comp in data:
                funcs[comp["name"]] = comp
    return funcs

def build_graph(funcs):
    G = nx.DiGraph()
    for name, comp in tqdm(funcs.items(), desc="Adding nodes"):
        G.add_node(name, **{
            "type_signature": comp.get("type_signature", ""),
            "type_dependencies": json.dumps(comp.get("type_dependencies", [])),
            "function_calls":     json.dumps([
                                        c["name"] if isinstance(c, dict) else c
                                        for c in comp.get("function_calls", [])
                                     ]),
            "where_definitions":  json.dumps([
                                        wd["name"] for wd in comp.get("where_definitions", [])
                                     ]),
            "start_line": comp.get("start_line", 0),
            "end_line":   comp.get("end_line", 0)
        })
    for caller, comp in tqdm(funcs.items(), desc="Adding edges"):
        for call in comp.get("function_calls", []):
            callee = call["name"] if isinstance(call, dict) else call
            if callee not in G:
                G.add_node(callee)
            G.add_edge(caller, callee)
    return G

def build_graph_from_schema(schema):
    G = nx.DiGraph()

    for node in schema["nodes"]:
        nid = node["id"]
        attrs = {}
        for k, v in node.items():
            if k == "id":
                continue
            if isinstance(v, (str, int, float, bool)):
                attrs[k] = v
            else:
                attrs[k] = json.dumps(v)
        G.add_node(nid, **attrs)

    for edge in schema["edges"]:
        src = edge["from"]
        dst = edge["to"]
        rel = edge.get("relation")
        G.add_edge(src, dst, relation=rel)
    return G