import argparse
import os
import pickle
import networkx as nx

def load_graph(graph_path):
    if graph_path.endswith(".gpickle"):
        with open(graph_path, "rb") as f:
            return pickle.load(f)
    elif graph_path.endswith(".graphml"):
        return nx.read_graphml(graph_path)
    else:
        raise RuntimeError(f"Unsupported graph format: {graph_path}")

def format_path(G, node_list):
    enriched = []
    for nid in node_list:
        mn = G.nodes[nid].get("module_name", "")
        fn = G.nodes[nid].get("file_name", "")
        if mn:
            enriched.append(f"{nid} (module: {mn})")
        elif fn:
            enriched.append(f"{nid} (file: {fn})")
        else:
            enriched.append(nid)
    return " -> ".join(enriched)

def find_from_single_source(G, source, target):
    return nx.shortest_path(G, source=source, target=target)

def find_path(graph_path, component, source=None, return_obj = False):
    G = load_graph(graph_path)
    target = component
    source = source

    if target not in G:
        print(f"Error: target '{target}' not in graph.")
        return

    if source:
        if source not in G:
            print(f"Error: source '{source}' not in graph.")
            return
        try:
            path = find_from_single_source(G, source, target)
            if return_obj:
                return path
            print("  " + format_path(G, path))
        except nx.NetworkXNoPath:
            print(f"No path found from '{source}' to '{target}'.")
    else:
        preds = list(G.predecessors(target))
        succs = list(G.successors(target))

        if preds:
            print(f"\nNodes with edges INTO '{target}' ({len(preds)}):")
            for p in preds:
                rel = G.get_edge_data(p, target).get("relation", "")
                print(f"  {p} --[{rel}]--> {target}")
        else:
            print(f"\nNo incoming edges to '{target}'.")

        if succs:
            print(f"\nNodes with edges OUT OF '{target}' ({len(succs)}):")
            for s in succs:
                rel = G.get_edge_data(target, s).get("relation", "")
                print(f"  {target} --[{rel}]--> {s}")
        else:
            print(f"\nNo outgoing edges from '{target}'.")