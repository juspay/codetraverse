from collections import defaultdict, Counter
from itertools import chain, combinations
from tqdm import tqdm


class FPNode:
    """A node in the FP-Tree."""
    def __init__(self, item, count, parent):
        self.item = item
        self.count = count
        self.parent = parent
        self.children = {}
        self.node_link = None

    def increment(self, count):
        """Increment the count of the node."""
        self.count += count

def find_frequent_items(transactions, min_support_count):

    item_counts = Counter(chain.from_iterable(transactions))
    frequent_items = {item: count for item, count in item_counts.items() if count >= min_support_count}
    return frequent_items

def build_fp_tree(transactions, frequent_items):
    """Build the FP-Tree and the header table."""
    # Header table stores item -> (count, node_link)
    header_table = {item: [count, None] for item, count in frequent_items.items()}
    
    # Create the root of the tree
    root = FPNode(None, 1, None)

    for transaction in transactions:
        # Filter and sort items in the transaction based on frequency
        sorted_items = sorted([item for item in transaction if item in frequent_items],
                              key=lambda x: frequent_items[x], reverse=True)
        
        if sorted_items:
            insert_tree(sorted_items, root, header_table)
            
    return root, header_table

def insert_tree(items, node, header_table):
    """Recursively insert a transaction into the FP-Tree."""
    if not items:
        return

    first_item = items[0]
    child = node.children.get(first_item)

    if child:
        # Node already exists, just increment count
        child.increment(1)
    else:
        # Create a new node
        child = FPNode(first_item, 1, node)
        node.children[first_item] = child
        
        # Update header table link
        if header_table[first_item][1] is None:
            header_table[first_item][1] = child
        else:
            # Find the last node in the chain and link to the new one
            current_node = header_table[first_item][1]
            while current_node.node_link is not None:
                current_node = current_node.node_link
            current_node.node_link = child

    # Recursively call for the rest of the items
    if len(items) > 1:
        insert_tree(items[1:], child, header_table)


def find_prefix_path(node):
    """Ascend the FP-Tree from a starting node to find its prefix path."""
    path = []
    while node and node.parent is not None:
        path.append(node.item)
        node = node.parent
    return path[1:] # Exclude the node itself, return the conditional pattern base

def mine_tree(header_table, min_support_count, prefix, frequent_itemsets):
    """Recursively mine the FP-Tree to find frequent itemsets."""
    # Get items from header table, sorted from least frequent to most
    sorted_items = sorted(list(header_table.keys()), key=lambda x: header_table[x][0])
    print("sorted")

    for item in sorted_items:
        new_frequent_set = prefix.copy()
        new_frequent_set.add(item)
        
        # Add the new frequent itemset to our results
        support_count = header_table[item][0]
        frequent_itemsets[frozenset(new_frequent_set)] = support_count
        
        # Find conditional pattern bases
        conditional_pattern_base = []
        current_node = header_table[item][1]
        while current_node is not None:
            prefix_path = find_prefix_path(current_node)
            if prefix_path:
                # The path contributes its count number of times
                for _ in range(current_node.count):
                    conditional_pattern_base.append(prefix_path)
            current_node = current_node.node_link
            
        # Build a conditional FP-Tree and mine it
        cond_frequent_items = find_frequent_items(conditional_pattern_base, min_support_count)
        print(cond_frequent_items)
        if cond_frequent_items:
            cond_tree, cond_header = build_fp_tree(conditional_pattern_base, cond_frequent_items)
            mine_tree(cond_header, min_support_count, new_frequent_set, frequent_itemsets)

def fpgrowth(transactions, min_support):

    num_transactions = len(transactions)
    min_support_count = min_support * num_transactions
    
    frequent_items = find_frequent_items(transactions, min_support_count)
    print("herer")
    if not frequent_items:
        return {}

    root, header_table = build_fp_tree(transactions, frequent_items)
    print("hello")
    frequent_itemsets = {}
    mine_tree(header_table, min_support_count, set(), frequent_itemsets)
    
    return frequent_itemsets