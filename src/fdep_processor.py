from pathlib import Path
import argparse
import os
import subprocess
import networkx as nx


CUR_PATH = os.path.abspath(__file__)
PICKLE_FILE_PATH = Path(CUR_PATH).parent / "graph.pickle"

def check_node() -> bool:
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True)
        if result.stdout:
            return True
        return False
    except:
        print("Unable to check node version. Please ensure node is installed and set in path")
        return False
    
def create_ts_fdep(js_path: str, tsconfig_path: str) -> tuple[bool, Path | None]:
    try:
        output_path = Path(CUR_PATH).parent
        result = subprocess.run(["node", js_path, tsconfig_path, "-o", str(output_path)], capture_output=True, text=True, check=True)
        if result.stdout:
            return (True, output_path / "fdep-output.json")
        return (False, None)
    except Exception as e:
        print(e)
        return (False, None)
    
def process_ts_output(output_pth: Path):
    if not output_pth.exists():
        print(output_pth, "doesn't exist")
        exit(1)

    import json
    from typing import Dict, Any

    content = json.loads(output_pth.read_text())
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
                node_type=node_dct.get("nodeType", "<NO-TYPE>")
            )
        for (src, dst) in ts_fdep.get("edges", []):
            graph.add_edge(src, dst)
        nx.write_graphml(graph, str(PICKLE_FILE_PATH))
        print(graph)

def create_python_fdep(codebase_dir: Path) -> bool:
    if not codebase_dir.exists():
        print(str(codebase_dir), "doesn't exist")
        exit(1)
    try:
        from py_fdep.fdep import build_project_graph
        import pickle

        graph = build_project_graph(str(codebase_dir))
        print(graph)
        with open(PICKLE_FILE_PATH, "wb") as f:
            pickle.dump(graph, f)
        return True
    except Exception as e:
        print(e)
        return False

def main():
    parser = argparse.ArgumentParser(description="Simple FDEP CLI")
    parser.add_argument("-l", "--lang", dest="language", choices=["python", "typescript"], required=True, type=str, help="Language of repo")
    parser.add_argument("-s", "--src", dest="source", required=True, type=str, help="Path of the project dir")
    args = parser.parse_args()

    pth = Path(args.source)
    if not pth.exists():
        print("No such path exists :", str(pth))
        exit(1)
    selected_language = args.language.lower()
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
            result, output_pth = create_ts_fdep(str(js_path), tsconfig_path)
            if result:
                process_ts_output(output_pth)
            else:
                print("Unable to create TS FDEP data")
                exit(1)
            
    elif selected_language == "python":
        status = create_python_fdep(pth)
        if not status:
            print("Unable to create PY FDEP data")
            exit(1)
    