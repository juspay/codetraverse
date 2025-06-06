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
    We stored those as node‐attributes.  If neither exists (unlikely), just print the ID.
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

def find_from_any_root(G, target):
    paths = {}
    roots = [n for (n, deg) in G.in_degree() if deg == 0]
    for r in roots:
        try:
            p = nx.shortest_path(G, source=r, target=target)
            paths[r] = p
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
    return paths

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
            if not quiet:
                print(f"Shortest path from '{source}' → '{target}':")
                print("  " + format_path(G, path))
            return path
        except nx.NetworkXNoPath:
            print(f"No path found from '{source}' to '{target}'.")
            return
    else:
        paths = find_from_any_root(G, target)
        if not paths:
            print(f"No path found from any root to '{target}'.")
            return
        if not quiet:
            print(f"Found path(s) to '{target}' from root node(s):")
            for root, p in paths.items():
                print(f"• Root = '{root}':")
                print("    " + format_path(G, p))
        return paths
