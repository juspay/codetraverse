import os
import json
import traceback
from typing import Dict, List, Optional, Union, Any
from tree_sitter import Language, Parser, Node
import tree_sitter_rescript
import tree_sitter_haskell
import tree_sitter_typescript
import tree_sitter_go
import tree_sitter_rust
from codetraverse.ast_diff.haskelldiff import HaskellFileDiff
from codetraverse.ast_diff.resdiffer import RescriptFileDiff
from codetraverse.ast_diff.TSdiff import TypeScriptFileDiff
from codetraverse.ast_diff.godiff import GoFileDiff
from codetraverse.ast_diff.rustdiff import RustFileDiff
from codetraverse.ast_diff.gitwrapper import GitWrapper
from codetraverse.ast_diff.bitbucket import BitBucket
from git import Repo
from unidiff import PatchSet
import argparse
import sys

class AstDiffOrchestrator:

    EXT_MAP = {
        "rescript":   ['.res'],
        "haskell":    ['.hs', '.lhs', '.hs-boot'],
        "typescript": ['.ts', '.tsx'],
        "go":         ['.go'],
        "rust":       ['.rs'],
    }

    INVERSE_EXTS = {ext: lang for lang, exts in EXT_MAP.items() for ext in exts}

    def __init__(self):
        # Maps the language name to its specific tools
        self.language_handlers = {
            "rescript":   {'lang_obj': Language(tree_sitter_rescript.language()), 'differ_class': RescriptFileDiff},
            "haskell":    {'lang_obj': Language(tree_sitter_haskell.language()), 'differ_class': HaskellFileDiff},
            "typescript": {'lang_obj': Language(tree_sitter_typescript.language_typescript()), 'differ_class': TypeScriptFileDiff},
            "go":         {'lang_obj': Language(tree_sitter_go.language()), 'differ_class': GoFileDiff},
            "rust":       {'lang_obj': Language(tree_sitter_rust.language()), 'differ_class': RustFileDiff},
        }
        
        # Pre-initialize a parser for each language handler
        self.parsers = {lang: Parser(handler['lang_obj']) for lang, handler in self.language_handlers.items()}
        
        # Special handling for TSX which uses a different language object but the same differ
        self.parsers['.tsx'] = Parser(Language(tree_sitter_typescript.language_tsx()))


    def _get_extension(self, filename: str) -> str:
        """Gets the primary extension for a given filename."""
        _, ext = os.path.splitext(filename)
        return ext

    def is_supported(self, filename: str) -> bool:
        """Checks if a file extension is supported."""
        return self._get_extension(filename) in self.INVERSE_EXTS

    def get_parser(self, filename: str) -> Parser:
        """Gets the appropriate parser for the file."""
        ext = self._get_extension(filename)
        # Handle the special case for .tsx parser
        if ext == '.tsx':
            return self.parsers['.tsx']
        
        lang = self.INVERSE_EXTS.get(ext)
        return self.parsers.get(lang)

    def get_differ(self, filename: str) -> Optional[Any]:
        """Gets an instance of the appropriate differ class for the file."""
        ext = self._get_extension(filename)
        lang = self.INVERSE_EXTS.get(ext)
        handler = self.language_handlers.get(lang)
        if handler:
            return handler['differ_class'](filename)
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

        print(changed_files)
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
        if provider_type == "bitbucket":
            bb_config = config.get("bitbucket", {})
            git_provider = BitBucket(
                base_url=bb_config.get("base_url"),
                project_key=bb_config.get("project_key"),
                repo_slug=bb_config.get("repo_slug"),
                auth=bb_config.get("auth"),
                headers=bb_config.get("headers", {"Accept": "application/json"})
            )
        elif provider_type == "local":
            local_config = config.get("local", {})
            git_provider = GitWrapper(repo_path=local_config.get("repo_path"))
        else:
            raise ValueError(f"Unsupported provider_type: '{provider_type}'. Must be 'bitbucket' or 'local'.")

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
        print(f"FATAL ERROR in configuration or execution: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Generate an Abstract Syntax Tree (AST) diff for code changes.")
    
    # Add a single argument to accept a JSON configuration string
    parser.add_argument("--config-json", help="A JSON string containing the configuration.")

    # Keep the existing subparsers for backward compatibility and direct CLI use
    subparsers = parser.add_subparsers(dest="provider_type", help="Specify the Git provider.")

    # --- Common arguments for both providers ---
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--output-dir", default="./ast_diff_output", help="Directory to save the output JSON file.")
    parent_parser.add_argument("--from-branch", help="The source branch name.")
    parent_parser.add_argument("--to-branch", help="The target branch name (e.g., main).")
    parent_parser.add_argument("--from-commit", help="The starting commit hash.")
    parent_parser.add_argument("--to-commit", help="The ending commit hash.")
    parent_parser.add_argument("--quiet", action="store_true", help="Suppress processing status messages.")

    # --- Subparser for local Git repository ---
    parser_local = subparsers.add_parser("local", parents=[parent_parser], help="Use a local Git repository.")
    parser_local.add_argument("repo_path", nargs='?', default=None, help="The file path to the local Git repository.")

    # --- Subparser for Bitbucket repository ---
    parser_bb = subparsers.add_parser("bitbucket", parents=[parent_parser], help="Use a remote Bitbucket repository.")
    parser_bb.add_argument("--base-url", help="Bitbucket server base URL.")
    parser_bb.add_argument("--project-key", help="Bitbucket project key.")
    parser_bb.add_argument("--repo-slug", help="Bitbucket repository slug.")
    parser_bb.add_argument("--user", help="Bitbucket username for authentication.")
    parser_bb.add_argument("--token", help="Bitbucket password or personal access token.")
    parser_bb.add_argument("--pr-id", help="Pull Request ID to automatically  commits.")

    args = parser.parse_args()

    if args.config_json:
        try:
            config_str = args.config_json

            # Try to parse once
            config = json.loads(config_str)

            # If still a string (i.e., double-encoded), parse again
            if isinstance(config, str):
                config = json.loads(config)

            if not isinstance(config, dict):
                raise ValueError("Config is not a valid odfvsdbbject.")

            run_ast_diff_from_config(config)

        except Exception as e:
            print(f"FATAL ERROR: Invalid JSON in --config-json argument: {e}", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)

    elif args.provider_type:
        # --- Construct the config dictionary from arguments (existing logic) ---
        config = {
            "provider_type": args.provider_type,
            "output_dir": args.output_dir,
            "quiet": args.quiet,
            "pr_id": getattr(args, 'pr_id', None),
            "from_branch": args.from_branch,
            "to_branch": args.to_branch,
            "from_commit": args.from_commit,
            "to_commit": args.to_commit,
        }

        if args.provider_type == "local":
            if not args.repo_path:
                parser.error("the following arguments are required: repo_path")
            config["local"] = {"repo_path": args.repo_path}
        elif args.provider_type == "bitbucket":
            if not all([args.base_url, args.project_key, args.repo_slug, args.user, args.token]):
                parser.error("missing required arguments for bitbucket provider.")
            config["bitbucket"] = {
                "base_url": args.base_url,
                "project_key": args.project_key,
                "repo_slug": args.repo_slug,
                "auth": (args.user, args.token)
            }
        
        run_ast_diff_from_config(config)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
        
# if __name__ == "__main__":
    
    
#     print("\n--- RUNNING EXAMPLE 1: LOCAL GIT REPO ---")
#     local_repo_config = {
#         "provider_type": "local",
#         "local": {
#             "repo_path": "/Users/pramod.p/xyne/"
#         },
#         "from_branch": "feat/dummy-sheet",
#         "to_branch": "main",
#         "output_dir": "./ast_diff_local_example",
#         "quiet": False
#     }
#     run_ast_diff_from_config(local_repo_config)
#     print("\n" + "="*50 + "\n")
    
#     print("\n" + "="*50 + "\n")

    # --- EXAMPLE 2: BITBUCKET PULL REQUEST ---
    # print("\n--- RUNNING EXAMPLE 2: BITBUCKET PULL REQUEST ---")
    
    # IMPORTANT: Replace these placeholder values with your actual Bitbucket details.
    # bitbucket_repo_config = {
    #     "provider_type": "bitbucket",
    #     "bitbucket": {
    #         "base_url": "https://bitbucket.juspay.net/rest",
    #         "project_key": "JBIZ",
    #         "repo_slug": "rescript-euler-dashboard",
    #         "auth": ("pramod.p@juspay.in","BBDC-Mzg1MDI2Mzk2MjQwOoonuqXjYa/7A+l03RwECSIiCBBH")# Or use your auth tuple
    #     },
    #     # The script will get the 'from' and 'to' commits from the PR
    #     "pr_id": "23584", 
    #     "output_dir": "./ast_diff_bitbucket_example",
    #     "quiet": False
    # }

    # run_ast_diff_from_config(bitbucket_repo_config)
