import os
import argparse
import networkx as nx
import pickle
from tqdm import tqdm

from registry.extractor_registry import get_extractor
from utils.networkx_graph import load_components, build_graph_from_schema
from adapters.haskell_adapter import adapt_haskell_components

os.environ["TOKENIZERS_PARALLELISM"] = "false"

parser = argparse.ArgumentParser(description="CodeTraverse")
parser.add_argument('--ROOT_DIR',   type=str, required=True)
parser.add_argument('--OUTPUT_BASE',type=str, default='fdep')
parser.add_argument('--GRAPH_DIR',  type=str, default='graph')
parser.add_argument('--LANGUAGE',   type=str, default='haskell')
args = parser.parse_args()

ROOT_DIR         = args.ROOT_DIR
OUTPUT_BASE      = args.OUTPUT_BASE
GRAPH_OUTPUT_DIR = args.GRAPH_DIR
LANGUAGE         = args.LANGUAGE.lower()

os.makedirs(OUTPUT_BASE, exist_ok=True)
os.makedirs(GRAPH_OUTPUT_DIR, exist_ok=True)

EXT = { 'haskell': '.hs' }.get(LANGUAGE, '')
extractor = get_extractor(LANGUAGE)

hs_files = []
for dirpath, _, filenames in os.walk(ROOT_DIR):
    for fn in filenames:
        if fn.endswith(EXT):
            hs_files.append(os.path.join(dirpath, fn))

for code_path in tqdm(hs_files, desc="Processing files"):
    extractor.process_file(code_path)
    rel_path = os.path.relpath(code_path, ROOT_DIR)
    json_rel = os.path.splitext(rel_path)[0] + ".json"
    out_path = os.path.join(OUTPUT_BASE, json_rel)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    extractor.write_to_file(out_path)

print(f"Done! All outputs in: {OUTPUT_BASE}/")

raw_funcs = list(load_components(OUTPUT_BASE).values())
if LANGUAGE == 'haskell':
    unified_schema = adapt_haskell_components(raw_funcs)
else:
    raise RuntimeError(f"No adapter for language: {LANGUAGE}")

G = build_graph_from_schema(unified_schema)
print(f"Graph has {G.number_of_nodes()} nodes and {G.number_of_edges()} edges")

graph_ml = os.path.join(GRAPH_OUTPUT_DIR, "repo_function_calls.graphml")
graph_gp = os.path.join(GRAPH_OUTPUT_DIR, "repo_function_calls.gpickle")

nx.write_graphml(G, graph_ml)
with open(graph_gp, "wb") as f:
    pickle.dump(G, f)

print(f"Wrote {graph_ml} and {graph_gp}")