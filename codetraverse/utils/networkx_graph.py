import os
import json
import networkx as nx
from codetraverse.adapters.rescript_adapter import extract_id
from networkx import DiGraph

def load_components(fdep_dir):

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


def preprocess_graph(G: nx.DiGraph) -> nx.DiGraph:
    """
    Removes nodes with empty code attributes from the graph.

    Args:
        G: Directed graph representing the codebase.

    Returns:
        The preprocessed graph with nodes having empty code removed.
    """
    nodes_to_remove = [node for node, attrs in G.nodes(data=True) if attrs.get("code", "") == ""]
    G.remove_nodes_from(nodes_to_remove)
    # print(f"Removed {len(nodes_to_remove)} nodes with empty code attribute during preprocessing")
    return G


def build_clean_graph(folder_path:str, save_as_json:bool = False, save_as_graphml:bool = False, output_path:str=""):

    json_folder = folder_path
    fdep_nx = build_graph_from_folder(json_folder, save_as_json=save_as_json, save_as_graphml=save_as_graphml, output_path=output_path)
    num_nodes = fdep_nx.number_of_nodes()
    # print(f"Total nodes in graph before preprocessing: {num_nodes}")
    
    # Preprocess the graph to remove nodes with empty code
    fdep_nx = preprocess_graph(fdep_nx)
    num_nodes_after = fdep_nx.number_of_nodes()
    # print(f"Total nodes in graph after preprocessing: {num_nodes_after}")
    
    root_nodes = [n for n, deg in fdep_nx.in_degree() if deg == 0]
    # print("Root nodes:", len(root_nodes))
    top5 = top_roots_by_descendants(fdep_nx, top_n=5)
    # for node, cnt in top5:
        # print(f"{node!r} has {cnt} descendants")
    
    return fdep_nx

def build_graph_from_folder(folder_path: str, save_as_json:bool = False, save_as_graphml:bool = False, output_path:str="") -> DiGraph:

    G = DiGraph()
    for root, dirs, files in os.walk(folder_path):
        for fname in files:
            if not fname.endswith(".json"):
                continue
            full_path = os.path.join(root, fname)
            try:
                with open(full_path, "r") as f:
                    data = json.load(f)
                process_module(data, G)
            except Exception as e:
                print(e)
                continue
    if save_as_json:
        graph_to_json(G, output_path)
    sanitize_for_graphml(G)
    if save_as_graphml:
        nx.write_graphml(G, f"{output_path}/fdep.graphml")
    return G

def graph_to_json(G: DiGraph, output_path) -> dict:
    out = {}
    for node in G.nodes():
        parents = list(G.predecessors(node))
        children = list(G.successors(node))
        attrs = G.nodes[node]
        module = attrs.get("module")
        if module is None and "--" in node:
            module = node.split("--", 1)[1]
        out[node] = {
            "parent_functions": parents,
            "children_functions": children,
            "data": {
                "code": attrs.get("code", ""),
                "type_signature": attrs.get("type_signature", ""),
                "module": module or ""
            }
        }
    with open(f"{output_path}/fdep.json", "w") as f:
        json.dump(out, f)
    return out

def sanitize_for_graphml(G: DiGraph) -> None:
    for n, attrs in G.nodes(data=True):
        for k, v in list(attrs.items()):
            if isinstance(v, list):
                attrs[k] = json.dumps(v)
    if G.is_multigraph():
        for u, v, key, attrs in G.edges(keys=True, data=True):
            for k, v in list(attrs.items()):
                if isinstance(v, list):
                    attrs[k] = json.dumps(v)
    else:
        for u, v, attrs in G.edges(data=True):
            for k, v in list(attrs.items()):
                if isinstance(v, list):
                    attrs[k] = json.dumps(v)

def add_line_num(node):
    res_code = []
    og_code = node.get("code", "")
    start = node.get("start_line", -1)
    end = node.get("end_line", -1)
    if start < 0 or end < 0:
        return og_code
    lines = og_code.splitlines()
    max_line_num_len = len(str(len(lines))) + 1
    for idx, line in enumerate(lines, start):
        line_num = str(idx).rjust(max_line_num_len)
        formatted_line = f"{line_num} | {line}"
        res_code.append(formatted_line)
    return "\n".join(res_code)

def add_or_update_node(G: DiGraph, key: str, meta: dict, merge_lists: bool = True):
    if not G.has_node(key):
        G.add_node(key, **meta)
        return
    existing = G.nodes[key]
    for k, v in meta.items():
        if merge_lists and isinstance(v, list) and isinstance(existing.get(k), list):
            existing[k] = list(set(existing[k]) | set(v))
        else:
            existing[k] = v

def process_module(module_data: list[dict], G: DiGraph):
    for node in module_data:
        if type(node) != dict:
            continue
        if node.get("kind") != "function":
            continue
        node_key = f"{node.get('name','_')}--{node.get('module','_')}"
        children = {
            f"{c.get('base','_')}--{c.get('modules',['_'])[0]}"
            for c in node.get("function_calls", [])
            if type(c) == dict and c.get("context") == "function_call"
        }
        node_meta = {
            "code": add_line_num(node),
            "type_signature": node.get("type_signature", ""),
            "types_used": node.get("type_dependencies", []),
        }
        add_or_update_node(G, node_key, node_meta, False)
        for ck in children:
            if not G.has_node(ck):
                G.add_node(ck)
            G.add_edge(node_key, ck)

def top_roots_by_descendants(G: nx.DiGraph, top_n: int = 10) -> list[tuple[str, int]]:
    roots = [n for n, deg in G.in_degree() if deg == 0]
    root_counts = []
    for r in roots:
        count = len(nx.descendants(G, r))
        root_counts.append((r, count))
    root_counts.sort(key=lambda x: x[1], reverse=False)
    return root_counts[:top_n]
