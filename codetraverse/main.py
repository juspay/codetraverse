import os
import networkx as nx
import pickle
from tqdm import tqdm
from codetraverse.registry.extractor_registry import get_extractor
from codetraverse.utils.networkx_graph import build_graph_from_schema, load_components_without_hash
from codetraverse.adapters.haskell_adapter import adapt_haskell_components
from codetraverse.adapters.python_adapter import adapt_python_components
from codetraverse.adapters.rescript_adapter import adapt_rescript_components
from codetraverse.adapters.rust_adapter import adapt_rust_components
from codetraverse.adapters.go_adapter import adapt_go_components
from codetraverse.adapters.typescript_adapter import adapt_typescript_components
from functools import reduce
import shutil
import traceback
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor


os.environ["TOKENIZERS_PARALLELISM"] = "false"

adapter_map = {
    "haskell": adapt_haskell_components,
    "python": adapt_python_components,
    "rescript": adapt_rescript_components,
    "rust": adapt_rust_components,
    "golang": adapt_go_components,
    "typescript": adapt_typescript_components
}

EXT_MAP = {'haskell': '.hs', 'python':  '.py', 'rescript': '.res', 'golang': '.go', 'rust': '.rs', 'typescript': '.ts'}
INVERSE_EXTS = {val: key for key, val in EXT_MAP.items()}

def combine_schemas(old, new):
    new_dict = {}
    new_dict["nodes"] = old["nodes"] + new["nodes"]
    new_dict["edges"] = old["edges"] + new["edges"]
    return new_dict

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


def create_fdep_data(root_dir, output_base: str = "./output/fdep", graph_dir: str = "./output/graph", clear_existing: bool = True):

    language_file_map = defaultdict(list)
    os.environ["ROOT_DIR"] = root_dir

    for dirpath, _, filenames in os.walk(root_dir):
        for file_name in filenames:
            extension = Path(file_name).suffix
            language = INVERSE_EXTS.get(extension, None)
            if language is not None:
                language_file_map[language].append(os.path.join(dirpath, file_name))

    if os.path.isdir(output_base) and clear_existing:
        shutil.rmtree(output_base, ignore_errors=True)
        shutil.rmtree(graph_dir, ignore_errors=True)

    os.makedirs(output_base, exist_ok=True)
    os.makedirs(graph_dir, exist_ok=True)

    for language in language_file_map:
        try:
            tasks_args = [(code_path, language, root_dir, output_base) for code_path in language_file_map[language]]

            with ProcessPoolExecutor() as executor:
                list(tqdm(executor.map(_process_single_file_worker, tasks_args), total=len(language_file_map[language]), desc=f"Processing - {language} - files"))
        except Exception as e:
            print(traceback.format_exc())
            print("ERROR -", e)

    print(f"Done! All outputs in: {output_base}")
    raw_funcs = load_components_without_hash(output_base)

    lang_comp_dict = defaultdict(list)
    for func in raw_funcs:
        comp_language = INVERSE_EXTS.get(Path(func["file_path"]).suffix, None)
        lang_comp_dict[comp_language].append(func)
    schemas = [
        adapter_map[language](comps) for language, comps in lang_comp_dict.items()
    ]

    unified_schema = reduce(combine_schemas, schemas)

    G = build_graph_from_schema(unified_schema)

    graph_ml = os.path.join(graph_dir, "repo_function_calls.graphml")
    graph_gp = os.path.join(graph_dir, "repo_function_calls.gpickle")

    nx.write_graphml(G, graph_ml)
    with open(graph_gp, "wb") as f:
        pickle.dump(G, f)

    print(f"Wrote {graph_ml} and {graph_gp}")