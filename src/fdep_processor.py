from pathlib import Path
import argparse
import os
import subprocess
import networkx as nx


CUR_PATH = os.path.abspath(__file__)

def check_node() -> bool:
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True)
        if result.stdout:
            return True
        return False
    except:
        print("Unable to check node version. Please ensure node is installed and set in path")
        return False
    
def create_ts_fdep(js_path: str, tsconfig_path: str, output_dir: str) -> tuple[bool, Path | None]:
    try:
        result = subprocess.run(["node", js_path, tsconfig_path, "-o", str(output_dir)], capture_output=True, text=True, check=True)
        if result.stdout:
            return (True, output_dir / "fdep-output.json")
        return (False, None)
    except Exception as e:
        print(e)
        return (False, None)
    
def process_ts_output(output_pth: Path, pickle_file_path: Path):
    if not output_pth.exists():
        print(output_pth, "doesn't exist")
        exit(1)

    import json
    from typing import Dict, Any

    if output_pth.exists():
        content = output_pth.read_text()
        ts_fdep: Dict[Any, Any] = json.loads(content)
        graph = nx.DiGraph()
        nodes_dct = ts_fdep.get("nodes", {})
        for node in nodes_dct:
            node_dct = nodes_dct[node]
            graph.add_node(
                node,
                file=node_dct.get("file", "<NO-FILE-PATH>"),
                label=node_dct.get("label", "<NO-LABEL>"),
                code=node_dct.get("code", "<NO-CODE>"),
                node_type=node_dct.get("node_type", "<NO-TYPE>")
            )
        for (src, dst) in ts_fdep.get("edges", []):
            if src != dst:
                graph.add_edge(src, dst)
        import pickle
        with open(pickle_file_path, "wb") as f:
            pickle.dump(graph, f)
        # nx.write_graphml(graph, str(pickle_file_path))
        print(graph)

def create_python_fdep(codebase_dir: Path, pickle_file_path: Path) -> bool:
    if not codebase_dir.exists():
        print(str(codebase_dir), "doesn't exist")
        exit(1)
    try:
        from py_fdep.fdep import build_project_graph
        import pickle

        graph = build_project_graph(str(codebase_dir), str(pickle_file_path.parent / "fdep.graphml"))
        print(graph)
        with open(pickle_file_path, "wb") as f:
            pickle.dump(graph, f)
        return True
    except Exception as e:
        print(e)
        return False

def main():
    parser = argparse.ArgumentParser(description="Simple FDEP CLI")
    parser.add_argument("-l", "--lang", dest="language", choices=["python", "typescript"], required=True, type=str, help="Language of repo")
    parser.add_argument("-s", "--src", dest="source", required=True, type=str, help="Path of the project dir")
    parser.add_argument("-o", "--outputDir", dest="output_dir", type=str, help="Path of output dir")
    parser.add_argument("-r", "--repoName", dest="repo_name", required=True, type=str, help="Name of the repo")
    args = parser.parse_args()

    pth = Path(args.source)
    if not pth.exists():
        print("No such path exists :", str(pth))
        exit(1)
    selected_language = args.language.lower()
    output_dir = Path(args.output_dir) if args.output_dir else Path(CUR_PATH).parent
    pickle_file_path = output_dir / f"{args.repo_name}_graph.pkl"
    if selected_language == "typescript":
        tsconfig_path = None
        for pth in pth.iterdir():
            if pth.name == "tsconfig.json":
                tsconfig_path = pth
        if tsconfig_path is None:
            print("No tsconfig file found in ", str(pth))
        print(tsconfig_path)
        if check_node():
            js_path = Path(CUR_PATH).parent / ".." / "dist" / "fdep.js"
            print(js_path)
            result, output_pth = create_ts_fdep(str(js_path), tsconfig_path, output_dir)
            if result:
                process_ts_output(output_pth, pickle_file_path)
            else:
                print("Unable to create TS FDEP data")
                exit(1)
            
    elif selected_language == "python":
        status = create_python_fdep(pth, pickle_file_path)
        if not status:
            print("Unable to create PY FDEP data")
            exit(1)

if __name__ == "__main__":
    main()