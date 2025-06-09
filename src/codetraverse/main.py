import os
import argparse
import networkx as nx
import pickle
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
from codetraverse.registry.extractor_registry import get_extractor
from codetraverse.utils.networkx_graph import load_components, build_graph_from_schema
from codetraverse.adapters.haskell_adapter import adapt_haskell_components
from codetraverse.adapters.python_adapter import adapt_python_components
from codetraverse.adapters.rescript_adapter import adapt_rescript_components

os.environ["TOKENIZERS_PARALLELISM"] = "false"

def _process_single_file_worker(args):
    code_path, language_str, root_dir_path, output_base_path = args
    extractor_instance = get_extractor(language_str)
    extractor_instance.process_file(code_path)
    rel_path = os.path.relpath(code_path, root_dir_path)
    json_rel = os.path.splitext(rel_path)[0] + ".json"
    out_path = os.path.join(output_base_path, json_rel)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    extractor_instance.write_to_file(out_path)
    return None

def create_fdep_data(root_dir, output_base="fdep", graph_output_dir="graph", language="haskell"):

    os.makedirs(output_base, exist_ok=True)
    os.makedirs(graph_output_dir, exist_ok=True)

    EXT_MAP = {'haskell': '.hs', 'python':  '.py', 'rescript': '.res'}
    EXT = EXT_MAP.get(language, '')

    hs_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.endswith(EXT):
                hs_files.append(os.path.join(dirpath, fn))

    # --
    tasks_args = [(code_path, language, root_dir, output_base) for code_path in hs_files]

    with ProcessPoolExecutor() as executor:
        list(tqdm(executor.map(_process_single_file_worker, tasks_args), total=len(hs_files), desc="Processing files"))

    print(f"Done! All outputs in: {output_base}/")
    # --
    
    raw_funcs = list(load_components(output_base).values())
    if language == 'haskell':
        unified_schema = adapt_haskell_components(raw_funcs)
    elif language == 'python':
        unified_schema = adapt_python_components(raw_funcs)
    elif language == 'rescript':
        unified_schema = adapt_rescript_components(raw_funcs)
    else:
        raise RuntimeError(f"No adapter for language: {language}")

    G = build_graph_from_schema(unified_schema)
    print(f"Graph has {G.number_of_nodes()} nodes and {G.number_of_edges()} edges")

    graph_gp = os.path.join(graph_output_dir, "repo_function_calls.gpickle")

    with open(graph_gp, "wb") as f:
        pickle.dump(G, f)