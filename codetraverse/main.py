import os
import networkx as nx
import pickle
from codetraverse.registry.extractor_registry import get_extractor
from codetraverse.utils.networkx_graph import build_graph_from_schema, load_components_without_hash
from codetraverse.adapters.haskell_adapter import adapt_haskell_components
from codetraverse.adapters.python_adapter import adapt_python_components
from codetraverse.adapters.rescript_adapter import adapt_rescript_components
from codetraverse.adapters.rust_adapter import adapt_rust_components
from codetraverse.adapters.go_adapter import adapt_go_components
from codetraverse.adapters.typescript_adapter import adapt_typescript_components
from codetraverse.adapters.purescript_adapter import adapt_purescript_components
from codetraverse.adapters.javascript_adapter import adapt_javascript_components

import pathspec
from functools import reduce
import shutil
import traceback
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import argparse
import sys

os.environ["TOKENIZERS_PARALLELISM"] = "false"

adapter_map = {
    "haskell": adapt_haskell_components,
    "python": adapt_python_components,
    "rescript": adapt_rescript_components,
    "rust": adapt_rust_components,
    "golang": adapt_go_components,
    "typescript": adapt_typescript_components,
    "purescript": adapt_purescript_components,
    "javascript": adapt_javascript_components
}

EXT_MAP = {
    "haskell": [".hs" , ".lhs" , ".hs-boot"],
    "python": [".py"],
    "rescript": [".res"],
    "golang": [".go"],
    "rust": [".rs"],
    "typescript": [".ts", ".tsx"],
    "purescript": [".purs"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"]
}

INVERSE_EXTS = {ext: lang for lang, exts in EXT_MAP.items() for ext in exts}

def combine_schemas(old, new):
    new_dict = {}
    new_dict["nodes"] = old["nodes"] + new["nodes"]
    new_dict["edges"] = old["edges"] + new["edges"]
    return new_dict

def _process_single_file_worker(args):
    code_path, language_str, root_dir_path, output_base_path = args
    try:
        extractor_instance = get_extractor(language_str)
        extractor_instance.process_file(code_path)
        rel_path = os.path.relpath(code_path, root_dir_path)
        json_rel = os.path.splitext(rel_path)[0] + ".json"
        out_path = os.path.join(output_base_path, json_rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        extractor_instance.write_to_file(out_path)
    except Exception as e:
        print(traceback.format_exc())
        print(f"Unable to process - {code_path}. Skipping it.")

def create_fdep_data(root_dir, output_base: str = "./output/fdep", graph_dir: str = "./output/graph", clear_existing: bool = True, skip_adaptor:bool = False):
    os.environ["ROOT_DIR"] = root_dir
    root_dir = Path(root_dir)
    language_file_map = defaultdict(list)
    gitignore_pth = root_dir / ".gitignore"
    gitign_pattern = gitignore_pth.read_text().splitlines() if gitignore_pth.exists() else []
    spec = pathspec.PathSpec.from_lines("gitwildmatch", gitign_pattern)

    for file_path in root_dir.rglob("*"):
        if not spec.match_file(str(file_path.relative_to(root_dir))):
            language = INVERSE_EXTS.get(file_path.suffix)
            if language:
                language_file_map[language].append(file_path)

    if os.path.isdir(output_base) and clear_existing:
        shutil.rmtree(output_base, ignore_errors=True)
        shutil.rmtree(graph_dir, ignore_errors=True)

    os.makedirs(output_base, exist_ok=True)
    os.makedirs(graph_dir, exist_ok=True)
    for language in language_file_map:
        try:
            tasks_args = [(code_path, language, root_dir, output_base) for code_path in language_file_map[language]]

            with ThreadPoolExecutor(max_workers=min(32, os.cpu_count() + 4)) as executor:
                list(executor.map(_process_single_file_worker, tasks_args))
        except Exception as e:
            print(traceback.format_exc())
            print("ERROR -", e)

    print(f"Done! All outputs in: {output_base}")
    if skip_adaptor:
        return

    raw_funcs = load_components_without_hash(output_base)

    lang_comp_dict = defaultdict(list)
    count_unprocessable_fucntion =0

    for func in raw_funcs:
        try:
            comp_language = INVERSE_EXTS.get(Path(func["file_path"]).suffix, None)
            lang_comp_dict[comp_language].append(func)
        except Exception as e:
            count_unprocessable_fucntion += 1
    print(f"Total unprocessable functions: {count_unprocessable_fucntion}")

    unsupported_languages = [lang for lang in lang_comp_dict if lang not in adapter_map]
    if unsupported_languages:
        print(f"Skipping unsupported languages: {unsupported_languages}")

    lang_comp_dict = {lang: comps for lang, comps in lang_comp_dict.items() if lang in adapter_map}

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

def main():
    parser = argparse.ArgumentParser(description='Create FDEP Data Tool')
    subparsers = parser.add_subparsers(dest='function', help='Available functions')

    # create_fdep_data
    parser_create = subparsers.add_parser('create_fdep_data', help='Create FDEP data from source code')
    parser_create.add_argument('root_dir', help='Root directory to scan for source files')
    parser_create.add_argument('--output_base', default='./output/fdep',
                              help='Output base directory (default: ./output/fdep)')
    parser_create.add_argument('--graph_dir', default='./output/graph',
                              help='Graph output directory (default: ./output/graph)')
    parser_create.add_argument('--no_clear', action='store_true',
                              help='Do not clear existing output directories')

    args = parser.parse_args()

    if not args.function:
        parser.print_help()
        return

    try:
        if args.function == 'create_fdep_data':
            # Convert --no_clear to clear_existing boolean
            clear_existing = not args.no_clear

            print(f"Creating FDEP data from: {args.root_dir}")
            print(f"Output base: {args.output_base}")
            print(f"Graph directory: {args.graph_dir}")
            print(f"Clear existing: {clear_existing}")

            create_fdep_data(
                root_dir=args.root_dir,
                output_base=args.output_base,
                graph_dir=args.graph_dir,
                clear_existing=clear_existing
            )

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def create_graph(fdep_dir, graph_dir):
    raw_funcs = load_components_without_hash(fdep_dir)

    lang_comp_dict = defaultdict(list)
    count_unprocessable_fucntion =0

    for func in raw_funcs:
        try:
            comp_language = INVERSE_EXTS.get(Path(func["file_path"]).suffix, None)
            lang_comp_dict[comp_language].append(func)
        except Exception as e:
            count_unprocessable_fucntion += 1
    print(f"Total unprocessable functions: {count_unprocessable_fucntion}")

    unsupported_languages = [lang for lang in lang_comp_dict if lang not in adapter_map]
    if unsupported_languages:
        print(f"Skipping unsupported languages: {unsupported_languages}")

    lang_comp_dict = {lang: comps for lang, comps in lang_comp_dict.items() if lang in adapter_map}

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

if __name__ == "__main__":
    main()
    # create_graph("/Users/jignyas.s/.xyne/c3c4ce677bbb8d1b88dc36118729f830/fdep", "/Users/jignyas.s/Desktop/Juspay/codetraverse")
    # create_fdep_data("/Users/jignyas.s/Desktop/Juspay/hyper-widget", "/Users/jignyas.s/Desktop/Juspay/codetraverse/output/fdep", "/Users/jignyas.s/Desktop/Juspay/codetraverse/output/graph")