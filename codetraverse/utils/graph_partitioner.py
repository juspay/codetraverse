import networkx as nx
import json
from typing import List, Dict
from statistics import mean, stdev
import random
from scipy.stats import norm

def add_code_length_attribute(graph: nx.DiGraph):
    """
    Add 'code_length' attribute to each node based on the 'code' attribute.
    Code length is the number of lines in the 'code' string after splitting by newline.
    
    Args:
        graph: A directed graph (nx.DiGraph) with nodes containing a 'code' attribute.
    """
    for node in graph.nodes():
        code = graph.nodes[node].get('code', '')
        if code:
            code_length = len(code.split('\n'))
        else:
            code_length = 0
        graph.nodes[node]['code_length'] = code_length

def compute_depth_from_root(graph: nx.DiGraph, node: str, visited: set, memo: dict) -> int:
    """
    Compute the longest path from any root to the node using DFS, ignoring cycles.
    
    Args:
        graph: Directed graph.
        node: Node to compute depth for.
        visited: Set of visited nodes to avoid cycles.
        memo: Dictionary for memoization to store computed depths.
    
    Returns:
        Length of the longest path from any root to the node.
    """
    if node in memo:
        return memo[node]
    
    if graph.in_degree(node) == 0:  # Node is a root
        memo[node] = 0
        return 0
    
    if node in visited:
        return 0  # Ignore cycle by treating as no path
    
    visited.add(node)
    max_depth = 0
    for parent in graph.predecessors(node):
        parent_depth = compute_depth_from_root(graph, parent, visited.copy(), memo)
        max_depth = max(max_depth, parent_depth + 1)
    visited.remove(node)
    
    memo[node] = max_depth
    return max_depth

def compute_depth_to_leaf(graph: nx.DiGraph, node: str, visited: set, memo: dict) -> int:
    """
    Compute the longest path from the node to any leaf using DFS, ignoring cycles.
    
    Args:
        graph: Directed graph.
        node: Node to compute depth from.
        visited: Set of visited nodes to avoid cycles.
        memo: Dictionary for memoization to store computed depths.
    
    Returns:
        Length of the longest path from the node to any leaf.
    """
    if node in memo:
        return memo[node]
    
    if graph.out_degree(node) == 0:  # Node is a leaf
        memo[node] = 0
        return 0
    
    if node in visited:
        return 0  # Ignore cycle by treating as no path
    
    visited.add(node)
    max_depth = 0
    for child in graph.successors(node):
        child_depth = compute_depth_to_leaf(graph, child, visited.copy(), memo)
        max_depth = max(max_depth, child_depth + 1)
    visited.remove(node)
    
    memo[node] = max_depth
    return max_depth

def compute_descendants(graph: nx.DiGraph, node: str, visited: set, memo: dict) -> int:
    """
    Compute the number of descendants (including the node itself) using DFS, ignoring cycles.
    
    Args:
        graph: Directed graph.
        node: Node to compute descendants for.
        visited: Set of visited nodes to avoid cycles.
        memo: Dictionary for memoization to store computed descendant counts.
    
    Returns:
        Number of descendants including the node itself.
    """
    if node in memo:
        return memo[node]
    
    if node in visited:
        return 0  # Ignore cycle
    
    visited.add(node)
    descendant_count = 1  # Count the node itself
    for child in graph.successors(node):
        descendant_count += compute_descendants(graph, child, visited.copy(), memo)
    visited.remove(node)
    
    memo[node] = descendant_count
    return descendant_count

def epsilon_greedy_selection(sorted_nodes_data, epsilon=0.2, num_selections=100):
    """
    Selects a list of representative nodes using the epsilon-greedy strategy.

    Args:
        sorted_nodes_data: List of node data dictionaries, sorted by 'metric' in descending order.
        epsilon: Probability of selecting a random node (exploration). Default is 0.2.
        num_selections: Number of nodes to select. Default is 100.

    Returns:
        A list of selected node data dictionaries.
    """
    selected = []
    unselected = sorted_nodes_data.copy()
    for _ in range(min(num_selections, len(sorted_nodes_data))):
        if random.random() < epsilon:
            # Exploration: select a random unselected node
            selected_node = random.choice(unselected)
        else:
            # Exploitation: select the highest-metric unselected node
            selected_node = unselected[0]
        selected.append(selected_node)
        unselected.remove(selected_node)
    return selected

def compute_node_metrics(graph: nx.DiGraph, epsilon:int = 0.2, num_selections=300) -> List[Dict]:
    """
    Compute a custom metric for each node in the graph based on the formula:
    metric = (1/distance_ratio) * (lines * (dependant_ratio**3) * hit_ratio * squashed_branch_factor)

    Args:
        graph: A directed graph (nx.DiGraph) with nodes having a 'code_length' attribute.

    Returns:
        A list of dictionaries, each containing node data and its computed metric, sorted descending by metric.
    """
    add_code_length_attribute(graph=graph)
    components = list(nx.weakly_connected_components(graph))
    all_nodes_data = []

    # Compute total descendants for all nodes in the entire graph
    total_descendants = {}
    for node in graph.nodes():
        total_descendants[node] = compute_descendants(graph, node, set(), {})

    # Compute levels (distance from root) for all nodes
    levels = {}
    for component in components:
        subgraph = graph.subgraph(component)
        roots = [n for n in subgraph.nodes() if subgraph.in_degree(n) == 0]
        for root in roots:
            for node in nx.bfs_tree(subgraph, root).nodes():
                levels[node] = nx.shortest_path_length(subgraph, root, node)

    # Compute average descendants per level in the entire graph
    level_descendants = {}
    for node, level in levels.items():
        if level not in level_descendants:
            level_descendants[level] = []
        level_descendants[level].append(total_descendants[node])
    avg_descendants_per_level = {level: mean(descendants) for level, descendants in level_descendants.items()}

    # Compute branch factors for all nodes
    branch_factors = {}
    for node in graph.nodes():
        parents = list(graph.predecessors(node))
        children = list(graph.successors(node))
        if children:
            avg_parents_children = mean(graph.in_degree(child) for child in children)
        else:
            avg_parents_children = 0
        if parents:
            avg_children_parents = mean(graph.out_degree(parent) for parent in parents)
        else:
            avg_children_parents = 0
        branch_factors[node] = avg_parents_children * avg_children_parents

    # Compute mean and std for branch factors
    branch_factor_values = list(branch_factors.values())
    mean_branch_factor = mean(branch_factor_values) if branch_factor_values else 0
    std_branch_factor = stdev(branch_factor_values) if len(branch_factor_values) > 1 else 1

    for component in components:
        subgraph = graph.subgraph(component)
        
        # Skip small subgraphs to avoid HITS errors
        if subgraph.number_of_nodes() < 2 or subgraph.number_of_edges() == 0:
            for node in subgraph.nodes():
                node_data = {
                    'node': node,
                    'metric': 0.0,
                    'distance_ratio': 0.0,
                    'dependant_ratio': 0.0,
                    'hit_ratio': 0.0,
                    'branch_factor': 0.0,
                    'squashed_branch_factor': 0.0,
                    'code_length': subgraph.nodes[node].get('code_length', 0),
                    'total_descendants': total_descendants.get(node, 0),
                    'level': levels.get(node, 0)
                }
                all_nodes_data.append(node_data)
            continue

        # 1. Depth from root
        depth_from_root = {}
        for node in subgraph.nodes():
            depth_from_root[node] = compute_depth_from_root(subgraph, node, set(), {})

        # 2. Depth to deepest leaf
        depth_to_leaf = {}
        for node in subgraph.nodes():
            depth_to_leaf[node] = compute_depth_to_leaf(subgraph, node, set(), {})

        # 3. HITS scores
        hub_scores, authority_scores = nx.hits(subgraph, max_iter=100, tol=1e-6, normalized=True)

        # 4. Code length
        code_lengths = nx.get_node_attributes(subgraph, 'code_length')

        # Compute metrics for each node
        for node in subgraph.nodes():
            d_root = depth_from_root.get(node, 1) + 1
            d_leaves = depth_to_leaf.get(node, 1) + 1 # Avoid division by zero
            distance_ratio = d_root / d_leaves if d_leaves > 0 else 0

            level = levels.get(node, 0)
            avg_descendants = avg_descendants_per_level.get(level, 1)
            current_descendants = compute_descendants(subgraph, node, set(), {})
            dependant_ratio = current_descendants / avg_descendants if avg_descendants > 0 else 0

            hub = hub_scores.get(node, 0)
            authority = authority_scores.get(node, 1) or 1e-15 # Avoid division by zero
            hit_ratio = hub / authority if authority > 0 else 0

            branch_factor = branch_factors.get(node, 0)
            squashed_branch_factor = norm.pdf(branch_factor, mean_branch_factor, std_branch_factor)

            lines = code_lengths.get(node, 0)

            # Compute the metric
            if distance_ratio > 0:
                metric = (1 / distance_ratio) * (lines * (dependant_ratio ** 2) * hit_ratio * squashed_branch_factor)
            else:
                metric = 0.0

            node_data = {
                "node": node,
                "metric": metric,
                # 'distance_ratio': (1 / distance_ratio),
                # 'd_root': d_root,
                # 'd_leaf': d_leaves,
                # 'dependant_ratio': dependant_ratio,
                # 'hit_ratio': hit_ratio,
                # 'branch_factor': branch_factor,
                # 'hub_score': hub,
                # 'authority_score': authority,
                # 'squashed_branch_factor': squashed_branch_factor,
                # 'branch_factor': branch_factor,
                # 'code_length': lines,
                # 'total_descendants': total_descendants.get(node, 0),
                # 'level': level
            }
            all_nodes_data.append(node_data)

    all_nodes_data.sort(key=lambda x: x['metric'], reverse=True)
    selected = epsilon_greedy_selection(sorted_nodes_data=all_nodes_data, epsilon=epsilon, num_selections=num_selections)
    res = {}
    for node in selected:
        node_attrs = graph.nodes[node["node"]]
        res[node["node"]] = {
                            'parent_functions': list(graph.predecessors(node["node"])),
                            # 'children_functions': list(graph.successors(node["node"])),
                            'data': {
                                'code': node_attrs.get('code', ''),
                                'type_signature': node_attrs.get('type_signature', '')
                                }
                            }
    # save_to_json(data=res, filename="top_custom_metric.json")
    return res

def save_to_json(data: List[Dict], filename: str):
    """
    Save the list of node data to a JSON file.

    Args:
        data: List of dictionaries containing node data.
        filename: Path to save the JSON file.
    """
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)