import os
import json
import traceback
from typing import Dict, List, Optional, Union, Any

# --- Tree-sitter setup ---
# Ensure you have installed the necessary packages:
# pip install tree-sitter gitpython unidiff
# pip install tree-sitter-rescript tree-sitter-haskell tree-sitter-typescript tree-sitter-go tree-sitter-rust
from tree_sitter import Language, Parser, Node
import tree_sitter_rescript
import tree_sitter_haskell
import tree_sitter_typescript
import tree_sitter_go
import tree_sitter_rust
from haskelldiff import HaskellFileDiff
from differ import RescriptFileDiff
from TSdiff import TypeScriptFileDiff
from godiff import GoFileDiff
from rustdiff import RustFileDiff
from gitwrapper import GitWrapper
from bitbucket import BitBucket
# --- Git and Diffing setup ---
from git import Repo
from unidiff import PatchSet

class AstDiffOrchestrator:
    """
    Manages and provides the correct parser and differ for multiple languages
    based on file extensions.
    """
    def __init__(self):
        # Central configuration for all supported languages
        self.language_config = {
            '.res': {'lang_obj': Language(tree_sitter_rescript.language()), 'differ_class': RescriptFileDiff},
            '.hs': {'lang_obj': Language(tree_sitter_haskell.language()), 'differ_class': HaskellFileDiff},
            '.ts': {'lang_obj': Language(tree_sitter_typescript.language_typescript()), 'differ_class': TypeScriptFileDiff},
            '.go': {'lang_obj': Language(tree_sitter_go.language()), 'differ_class': GoFileDiff},
            '.rs': {'lang_obj': Language(tree_sitter_rust.language()), 'differ_class': RustFileDiff},
        }
        # Pre-initialize a parser for each language
        self.parsers = {ext: Parser(config['lang_obj']) for ext, config in self.language_config.items()}

    def _get_extension(self, filename: str) -> str:
        """Gets the primary extension for a given filename."""
        _, ext = os.path.splitext(filename)
        return ext

    def is_supported(self, filename: str) -> bool:
        """Checks if a file extension is supported."""
        return self._get_extension(filename) in self.language_config

    def get_parser(self, filename: str) -> Parser:
        """Gets the appropriate parser for the file."""
        return self.parsers.get(self._get_extension(filename))

    def get_differ(self, filename: str) -> Optional[Any]:
        """Gets an instance of the appropriate differ class for the file."""
        config = self.language_config.get(self._get_extension(filename))
        if config:
            return config['differ_class'](filename)
        return None
    
def generate_ast_diff(
    git_provider: Union[BitBucket, GitWrapper],
    output_dir: str = "./",
    quiet: bool = True,
    pr_id: str = None,
    from_branch: str = None,
    to_branch: str = None,
    from_commit: str = None,
    to_commit: str = None,
):
    orchestrator = AstDiffOrchestrator()
    try:
        # --- 1. Determine Commits ---
        if not from_commit or not to_commit:
            if isinstance(git_provider, BitBucket):
                if pr_id:
                    pull_request = git_provider.get_pr_bitbucket(pr_id)
                    to_commit, from_commit = pull_request["fromRef"]["latestCommit"], pull_request["toRef"]["latestCommit"]
                else:
                    to_commit = git_provider.get_latest_commit_from_branch(from_branch)
                    from_commit = git_provider.get_latest_commit_from_branch(to_branch)
            elif isinstance(git_provider, GitWrapper):
                if pr_id: raise ValueError("PR IDs only supported for BitBucket.")
                to_commit = git_provider.get_latest_commit_from_branch(from_branch)
                from_commit = git_provider.get_common_ancestor(from_branch, to_branch)
            else:
                raise TypeError("Unsupported git_provider object.")

        print(f"Comparing commits: {from_commit[:7]} (old) -> {to_commit[:7]} (new)")

        # --- 2. Get Changed Files ---
        changed_files = git_provider.get_changed_files_from_commits(to_commit, from_commit)
        all_changes = []

        # --- 3. Process Files ---
        for category in ["modified", "added", "deleted"]:
            for file_path in changed_files.get(category, []):
                if not orchestrator.is_supported(file_path): continue

                parser = orchestrator.get_parser(file_path)
                differ = orchestrator.get_differ(file_path)

                if category == "modified":
                    old_content = git_provider.get_file_content(file_path, from_commit)
                    new_content = git_provider.get_file_content(file_path, to_commit)
                    if old_content is None or new_content is None: continue
                    old_ast = parser.parse(old_content.encode())
                    new_ast = parser.parse(new_content.encode())
                    changes = differ.compare_two_files(old_ast, new_ast)
                else:
                    commit = to_commit if category == "added" else from_commit
                    content = git_provider.get_file_content(file_path, commit)
                    if content is None: continue
                    ast = parser.parse(content.encode())
                    changes = differ.process_single_file(ast, mode=category)
                
                if changes:
                    all_changes.append(changes.to_dict())
                if not quiet: print(f"PROCESSED {category.upper()} FILE ({file_path})")

        # --- 4. Write Output File ---
        os.makedirs(output_dir, exist_ok=True)
        final_output_path = os.path.join(output_dir, "detailed_changes.json")
        with open(final_output_path, "w") as f: json.dump(all_changes, f, indent=2)
        print(f"Changes written to - {final_output_path}")

    except Exception as e:
        print(f"ERROR - {e}")
        traceback.print_exc()

def run_ast_diff_from_config(config: Dict[str, Any]):
    print("--- Starting AST Diff Generation from Config ---")
    provider_type = config.get("provider_type")
    git_provider = None

    try:
        # --- 1. Initialize Git Provider from Config ---
        if provider_type == "bitbucket":
            bb_config = config.get("bitbucket", {})
            git_provider = BitBucket(
                base_url=bb_config.get("base_url"),
                project_key=bb_config.get("project_key"),
                repo_slug=bb_config.get("repo_slug"),
                token=bb_config.get("token")
            )
        elif provider_type == "local":
            local_config = config.get("local", {})
            git_provider = GitWrapper(repo_path=local_config.get("repo_path"))
        else:
            raise ValueError(f"Unsupported provider_type: '{provider_type}'. Must be 'bitbucket' or 'local'.")

        # --- 2. Call the Core Function with Parameters from Config ---
        generate_ast_diff(
            git_provider=git_provider,
            output_dir=config.get("output_dir", "./ast_diff_output"),
            quiet=config.get("quiet", False),
            pr_id=config.get("pr_id"),
            from_branch=config.get("from_branch"),
            to_branch=config.get("to_branch"),
            from_commit=config.get("from_commit"),
            to_commit=config.get("to_commit"),
        )
        print("--- AST Diff Generation Finished ---")

    except Exception as e:
        print(f"FATAL ERROR in configuration or execution: {e}")
        traceback.print_exc()
        
# if __name__ == "__main__":
    
    
#     print("\n--- RUNNING EXAMPLE 1: LOCAL GIT REPO ---")
#     local_repo_config = {
#         "provider_type": "local",
#         "local": {
#             "repo_path": "/Users/pramod.p/euler-api-gateway"
#         },
#         "from_branch": "EUL-16517-dsl",
#         "to_branch": "staging",
#         "output_dir": "./ast_diff_local_example",
#         "quiet": False
#     }
#     run_ast_diff_from_config(local_repo_config)
#     print("\n" + "="*50 + "\n")