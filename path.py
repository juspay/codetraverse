import argparse
import os
import pickle
import networkx as nx

def load_graph(graph_path):
    """
    Loads a NetworkX graph from either a .gpickle or a .graphml file.
    """
    if graph_path.endswith(".gpickle"):
        with open(graph_path, "rb") as f:
            G = pickle.load(f)
    elif graph_path.endswith(".graphml"):
        G = nx.read_graphml(graph_path)
    else:
        raise RuntimeError(f"Unsupported graph format: {graph_path}")
    return G

def resolve_component_name(G, component_spec):
    """
    Resolve a component specification to an actual node ID.
    
    Args:
        G: NetworkX graph
        component_spec: Either a direct node ID or "file_name::component_name" format
    
    Returns:
        The actual node ID if found, otherwise None
    """
    # If it doesn't contain "::", treat it as a direct node ID
    if "::" not in component_spec:
        return component_spec if component_spec in G else None
    
    # Parse file_name::component_name format
    try:
        file_name, component_name = component_spec.split("::", 1)
    except ValueError:
        return None
    
    # Search for a node that matches both file_name and component_name
    matches = []
    for node_id in G.nodes():
        attrs = G.nodes[node_id]
        node_file = attrs.get("file_name")
        
        # Check if this node matches the file and component name
        if node_file == file_name and node_id == component_name:
            return node_id
        
        # Also check if the node_id itself contains the component name
        if node_file == file_name and component_name in node_id:
            matches.append(node_id)
        
        # Store potential matches for debugging
        if node_file and (file_name in node_file or node_file in file_name):
            if component_name in node_id:
                matches.append(f"POTENTIAL: {node_id} in file {node_file}")
    
    # If we have exact matches, return the first one
    exact_matches = [m for m in matches if not m.startswith("POTENTIAL:")]
    if exact_matches:
        return exact_matches[0]
    
    # Print debug info if no exact match found
    if matches:
        print(f"DEBUG: Potential matches for {component_spec}:")
        for match in matches:
            print(f"  {match}")
    
    return None

def find_from_any_root(G, target):
    """
    Find the shortest path from any root (in-degree == 0) to `target`.
    Returns a dict: {root: [path_nodes]}, choosing only those roots
    that actually reach `target`.
    """
    paths = {}
    roots = [n for n, deg in G.in_degree() if deg == 0]
    for root in roots:
        try:
            path = nx.shortest_path(G, source=root, target=target)
            paths[root] = path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
    return paths

def find_from_single_source(G, source, target):
    """
    Find the shortest path from one specific source to target.
    Returns the list of nodes if found, otherwise raises NetworkXNoPath.
    """
    return nx.shortest_path(G, source=source, target=target)

def main():
    parser = argparse.ArgumentParser(
        description="Given a saved function-call graph, find a path to a component."
    )
    parser.add_argument(
        "--GRAPH_PATH", "-g",
        type=str,
        required=True,
        help="Path to the saved graph (.gpickle or .graphml)."
    )
    parser.add_argument(
        "--COMPONENT", "-c",
        type=str,
        required=True,
        help="Target component name. Use 'file_name::component_name' format or direct node ID."
    )
    parser.add_argument(
        "--SOURCE", "-s",
        type=str,
        default=None,
        help="(Optional) Source component name. Use 'file_name::component_name' format or direct node ID. If omitted, searches from any root."
    )

    args = parser.parse_args()
    graph_path = args.GRAPH_PATH
    target_spec = args.COMPONENT
    source_spec = args.SOURCE

    if not os.path.isfile(graph_path):
        print(f"Error: graph file not found at {graph_path}")
        return

    G = load_graph(graph_path)

    # Resolve target component
    target = resolve_component_name(G, target_spec)
    if target is None:
        print(f"Error: target component '{target_spec}' could not be resolved in the graph.")
        if "::" in target_spec:
            file_name, component_name = target_spec.split("::", 1)
            print(f"  Looked for file '{file_name}' with component '{component_name}'")
        return

    # Resolve source component if specified
    source = None
    if source_spec:
        source = resolve_component_name(G, source_spec)
        if source is None:
            print(f"Error: source component '{source_spec}' could not be resolved in the graph.")
            if "::" in source_spec:
                file_name, component_name = source_spec.split("::", 1)
                print(f"  Looked for file '{file_name}' with component '{component_name}'")
            return

    def format_node(node_id):
        """
        Given a node ID, return a string that includes:
          • node ID itself
          • its file_name (if present)
          • its file_path (if present)
        """
        attrs = G.nodes[node_id]
        parts = [node_id]
        fn = attrs.get("file_name")
        if fn is not None:
            parts.append(f"(file: {fn})")
        fp = attrs.get("file_path")
        if fp is not None:
            parts.append(f"(path: {fp})")
        return " ".join(parts)

    def format_path(path):
        """
        Join a list of node IDs into a single string, with each ID
        enriched by module_name and file_path.
        """
        return " → ".join(format_node(n) for n in path)

    print(f"Resolved target: '{target_spec}' -> '{target}'")
    if source_spec:
        print(f"Resolved source: '{source_spec}' -> '{source}'")

    if source:
        try:
            path = find_from_single_source(G, source, target)
            print(f"\nShortest path from '{source}' to '{target}':")
            print(f"  {format_path(path)}")
        except nx.NetworkXNoPath:
            print(f"No path found from '{source}' to '{target}'.")
    else:
        paths = find_from_any_root(G, target)
        if not paths:
            print(f"No path found from any root to '{target}'.")
            return

        print(f"\nFound path(s) to '{target}' from the following root(s):")
        for root, path in paths.items():
            # Print root line including its file_name/file_path if any
            root_attrs = G.nodes[root]
            rn_parts = [root]
            rn_fn = root_attrs.get("file_name")
            if rn_fn is not None:
                rn_parts.append(f"(file: {rn_fn})")
            rn_fp = root_attrs.get("file_path")
            if rn_fp is not None:
                rn_parts.append(f"(path: {rn_fp})")
            print("• Root =", " ".join(rn_parts))
            print(f"    {format_path(path)}")

if __name__ == "__main__":
    main()