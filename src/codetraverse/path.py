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
    """
    Annotate each node in node_list with its module_name (if present) or file_name.
    We stored those as node‐attributes. If neither exists, just print the ID itself.
    """
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
    return " → ".join(enriched)

def find_from_single_source(G, source, target):
    return nx.shortest_path(G, source=source, target=target)

def find_path(graph_path, component, source=None, quiet=True):
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
            path_arr = []
            final_str = f"Shortest path from '{source}' → '{target}':\n  " + format_path(G, path)
            if not quiet:
                print(final_str)
                path_arr.append(final_str)
            return (path, final_str, None, None)
        except nx.NetworkXNoPath:
            print(f"No path found from '{source}' to '{target}'.")
            return
    else:
        preds = list(G.predecessors(target))
        preds_str_arr = []

        succs = list(G.successors(target))
        succs_str_arr = []

        if preds:
            if not quiet:
                print(f"\nNodes with edges INTO '{target}' ({len(preds)}):")
            for p in preds:
                rel = G.get_edge_data(p, target).get("relation", "")
                edge = f"{p} --[{rel}]--> {target}"
                if not quiet:
                    print(f"  {edge}")
                preds_str_arr.append(edge)
        else:
            if not quiet:
                print(f"\nNo incoming edges to '{target}'.")

        if succs:
            if not quiet:
                print(f"\nNodes with edges OUT OF '{target}' ({len(succs)}):")
            for s in succs:
                rel = G.get_edge_data(target, s).get("relation", "")
                edge = f"{target} --[{rel}]--> {s}"
                if not quiet:
                    print(f"  {edge}")
                succs_str_arr.append(edge)
        else:
            if not quiet:
                print(f"\nNo outgoing edges from '{target}'.")
        return (preds, preds_str_arr, succs, succs_str_arr)