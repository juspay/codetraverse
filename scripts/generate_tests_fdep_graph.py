#!/usr/bin/env python
import argparse
from codetraverse.main import create_fdep_data

parser = argparse.ArgumentParser()
parser.add_argument("--root-dir",   required=True, help="path to sample_code_repo_test/<lang>")
parser.add_argument("--out-fdep",   required=True, help="where to dump fdep JSON")
parser.add_argument("--out-graph",  required=True, help="where to dump GraphML")
args = parser.parse_args()

# note: we ignore any --lang flag, we just drive off root-dir name if you like
create_fdep_data(
    root_dir   = args.root_dir,
    output_base= args.out_fdep,
    graph_dir  = args.out_graph,
    clear_existing=True
)
