import os
import json
import traceback
from typing import Dict, List, Optional, Union, Any
from tree_sitter import Language, Parser, Node
# import tree_sitter_rescript
from tree_sitter_language_pack import get_language
from codetraverse.ast_diff.haskelldiff import HaskellFileDiff
from codetraverse.ast_diff.resdiffer import RescriptFileDiff
from codetraverse.ast_diff.TSdiff import TypeScriptFileDiff
from codetraverse.ast_diff.godiff import GoFileDiff
from codetraverse.ast_diff.rustdiff import RustFileDiff
from codetraverse.ast_diff.purescriptdiff import PureScriptFileDiff
from codetraverse.ast_diff.pythondiff import PythonFileDiff
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
        "python":     ['.py'],
        "purescript": ['.purs']
    }

    INVERSE_EXTS = {ext: lang for lang, exts in EXT_MAP.items() for ext in exts}

    def __init__(self):
        # Maps the language name to its specific tools
        self.language_handlers = {
            # "rescript":   {'lang_obj': Language(tree_sitter_rescript.language()), 'differ_class': RescriptFileDiff},
            "haskell":    {'lang_obj':  get_language('haskell'), 'differ_class': HaskellFileDiff},
            "typescript": {'lang_obj':  get_language('typescript'), 'differ_class': TypeScriptFileDiff},
            "go":         {'lang_obj': get_language('go'), 'differ_class': GoFileDiff},
            "rust":       {'lang_obj': get_language('rust'), 'differ_class': RustFileDiff},
            "python":     {'lang_obj':  get_language('python'), 'differ_class': PythonFileDiff},
        }
        
        # Pre-initialize a parser for each language handler
        self.parsers = {lang: Parser(handler['lang_obj']) for lang, handler in self.language_handlers.items()}
        
        # Special handling for TSX which uses a different language object but the same differ
        self.parsers['.tsx'] = Parser(get_language('tsx'))


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


def extract_components_from_file(file_path: str) -> Dict[str, Any]:
    """
    Extract top-level components (classes, functions, etc.) from a single file.
    
    Args:
        file_path (str): Path to the source code file
        
    Returns:
        dict: Dictionary containing extracted components organized by type
    """
    
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    
    # Initialize the orchestrator
    orchestrator = AstDiffOrchestrator()
    
    # Check if the file type is supported
    if not orchestrator.is_supported(file_path):
        return {"error": f"Unsupported file type: {file_path}"}
    
    # Get the appropriate parser and differ for this file type
    parser = orchestrator.get_parser(file_path)
    differ = orchestrator.get_differ(file_path)
    
    if not parser or not differ:
        return {"error": f"Could not get parser/differ for: {file_path}"}
    
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the file into an AST
        ast = parser.parse(content.encode('utf-8'))
        
        # Extract components using the language-specific differ
        components = differ.extract_components(ast.root_node)
        
        # Convert to a more readable format
        result = {
            "file_path": file_path,
            "language": orchestrator.INVERSE_EXTS.get(orchestrator._get_extension(file_path), "unknown"),
            "components": {}
        }
        
        # Handle different return formats from different languages
        if isinstance(components, dict):
            # Some languages return a dict of component types
            for component_type, items in components.items():
                if items:  # Only include non-empty categories
                    result["components"][component_type] = []
                    for name, data in items.items():
                        # data is typically (node, text, start_point, end_point)
                        if isinstance(data, tuple) and len(data) >= 4:
                            result["components"][component_type].append({
                                "name": name,
                                "start_line": data[2][0] + 1,  # Convert 0-based to 1-based
                                "end_line": data[3][0] + 1,
                                "content": data[1],  # Full content instead of preview
                                "start_byte": data[2][1] if len(data[2]) > 1 else 0,
                                "end_byte": data[3][1] if len(data[3]) > 1 else 0
                            })
        elif isinstance(components, tuple):
            # Handle different language-specific tuple formats
            language = result["language"]
            
            if language == "haskell":
                # For Haskell: functions, data_types, type_classes, instances, imports, template_haskell
                component_names = ["functions", "dataTypes", "typeClasses", "instances", "imports", "templateHaskell"]
            elif language == "typescript":
                # For TypeScript: functions, classes, interfaces, types, enums, constants, fields
                component_names = ["functions", "classes", "interfaces", "types", "enums", "constants", "fields"]
            else:
                # Default mapping for other languages
                component_names = ["functions", "classes", "types", "variables", "imports", "constants"]
            
            for i, component_dict in enumerate(components):
                if i < len(component_names) and component_dict:
                    component_type = component_names[i]
                    result["components"][component_type] = []
                    for name, data in component_dict.items():
                        if isinstance(data, tuple) and len(data) >= 4:
                            result["components"][component_type].append({
                                "name": name,
                                "start_line": data[2][0] + 1,
                                "end_line": data[3][0] + 1,
                                "content": data[1],  # Full content instead of preview
                                "start_byte": data[2][1] if len(data[2]) > 1 else 0,
                                "end_byte": data[3][1] if len(data[3]) > 1 else 0
                            })
        
        return result
        
    except Exception as e:
        return {"error": f"Error processing file {file_path}: {str(e)}"}


def extract_components_from_files(file_paths: List[str]) -> List[Dict[str, Any]]:
    """
    Extract top-level components from multiple files.
    
    Args:
        file_paths (List[str]): List of file paths to process
        
    Returns:
        List[Dict[str, Any]]: List of extraction results for each file
    """
    results = []
    
    for file_path in file_paths:
        try:
            result = extract_components_from_file(file_path)
            results.append(result)
        except Exception as e:
            error_result = {
                "file_path": file_path,
                "error": f"Error processing file {file_path}: {str(e)}"
            }
            results.append(error_result)
    
    return results


def generate_ast_diff(
    git_provider: Union[BitBucket, GitWrapper],
    output_dir: str = "./",
    quiet: bool = True,
    pr_id: str = None,
    from_branch: str = None,
    to_branch: str = None,
    from_commit: str = None,
    to_commit: str = None,
    write_to_file: bool = True,
) -> List[Dict[str, Any]]:
    orchestrator = AstDiffOrchestrator()
    all_changes = []
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
        
        # --- 2.5 Get Structured Diff for fallback ---
        structured_diff_added, structured_diff_removed = git_provider.get_structured_diff(from_commit, to_commit)

        # print("files",changed_files)
        # --- 3. Process Files ---
        for category in ["modified", "added", "deleted"]:
            for file_path in changed_files.get(category, []):
                if file_path.endswith(".lock"):
                    continue
                parser = orchestrator.get_parser(file_path)
                differ = orchestrator.get_differ(file_path)
                
                print(parser)
                if not parser or not differ:
                    if category == "modified":
                        added_lines = structured_diff_added.get(file_path, [])
                        removed_lines = structured_diff_removed.get(file_path, [])

                        if added_lines or removed_lines:
                            removed_str = "\n".join([line for _, line in removed_lines])
                            added_str = "\n".join([line for _, line in added_lines])

                            change_dict = {
                                "moduleName": file_path,
                                "modifiedFunctions": [
                                    [
                                        file_path,
                                        removed_str,
                                        added_str,
                                        {}
                                    ]
                                ]
                            }
                            all_changes.append(change_dict)
                    else: # added or deleted
                        content = git_provider.get_file_content(file_path, to_commit if category == "added" else from_commit)
                        if content is None: continue
                        
                        change_dict = {
                            "moduleName": file_path,
                            "addedFunctions" if category == "added" else "deletedFunctions": [
                                [
                                    file_path,
                                    content,
                                    {}
                                ]
                            ]
                        }
                        all_changes.append(change_dict)

                    if not quiet: print(f"PROCESSED UNSUPPORTED {category.upper()} FILE ({file_path}) using text diff")
                    continue

                if category == "modified":
                    old_content = None
                    new_content = None
                    try:
                        old_content = git_provider.get_file_content(file_path, from_commit)
                    except FileNotFoundError:
                        pass
                    try:
                        new_content = git_provider.get_file_content(file_path, to_commit)
                    except FileNotFoundError:
                        pass

                    if old_content and new_content:
                        old_ast = parser.parse(old_content.encode())
                        new_ast = parser.parse(new_content.encode())
                        changes = differ.compare_two_files(old_ast, new_ast)
                    elif new_content: # old_content is None
                        ast = parser.parse(new_content.encode())
                        changes = differ.process_single_file(ast, mode='added')
                    elif old_content: # new_content is None
                        ast = parser.parse(old_content.encode())
                        changes = differ.process_single_file(ast, mode='deleted')
                    else:
                        continue
                else: # added or deleted
                    commit = to_commit if category == "added" else from_commit
                    content = git_provider.get_file_content(file_path, commit)
                    if content is None: continue
                    ast = parser.parse(content.encode())
                    changes = differ.process_single_file(ast, mode=category)
                
                if changes:
                    all_changes.append(changes.to_dict())
                if not quiet: print(f"PROCESSED {category.upper()} FILE ({file_path})")
        
        return all_changes

    except Exception as e:
        print(f"ERROR - {e}")
        traceback.print_exc()
        return [] # Return empty list on error


def generate_ast_diff_for_commits(
    from_commit: str,
    to_commit: str,
    repo_path: str,
    output_dir: str = "./ast_diff_output",
    quiet: bool = False,
    write_to_file: bool = False,
) -> List[Dict[str, Any]]:
    """
    A simplified wrapper to generate an AST diff between two specific commits in a local repository.

    Args:
        from_commit (str): The older commit hash.
        to_commit (str): The newer commit hash.
        repo_path (str): The file path to the local Git repository.
        output_dir (str, optional): Directory to save the output. Defaults to "./ast_diff_output".
        quiet (bool, optional): Suppress status messages. Defaults to False.
        write_to_file (bool, optional): Whether to write the results to a JSON file. Defaults to True.
    
    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary represents the changes for a file.
    """
    print(f"--- Starting AST Diff for Commits in Repo: {repo_path} ---")
    try:
        # Initialize the GitWrapper for the local repository
        git_provider = GitWrapper(repo_path=repo_path)

        # Call the main diff generation function and capture the returned changes
        all_changes = generate_ast_diff(
            git_provider=git_provider,
            from_commit=from_commit,
            to_commit=to_commit,
            output_dir=output_dir,
            quiet=quiet,
            write_to_file=write_to_file
        )
        print("--- AST Diff Generation Finished ---")
        if write_to_file:
            final_output_path = os.path.join(output_dir, "detailed_changes.json")
            print(f"INFO: The detailed AST diff has been saved to '{final_output_path}'")
        
        print("INFO: The function is returning the following summary:")
        print(json.dumps(all_changes, indent=2))
        
        return all_changes

    except Exception as e:
        print(f"FATAL ERROR during AST diff generation: {e}", file=sys.stderr)
        traceback.print_exc()
        return []


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

        all_changes = generate_ast_diff(
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
        
        print(f"\n\n\n {all_changes}")
        return all_changes

    except Exception as e:
        print(f"FATAL ERROR in configuration or execution: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Generate an Abstract Syntax Tree (AST) diff for code changes or extract components.")
    
    # Add a single argument to accept a JSON configuration string
    parser.add_argument("--config-json", help="A JSON string containing the configuration.")
    
    # Add arguments for component extraction
    parser.add_argument("--extract-components", action="store_true", help="Extract components from files instead of generating diff.")
    parser.add_argument("--file", help="Single file to extract components from.")
    parser.add_argument("--files", nargs='+', help="Multiple files to extract components from.")
    parser.add_argument("--output-file", help="Output file to save component extraction results.")

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
                raise ValueError("Config is not a valid object.")

            run_ast_diff_from_config(config)

        except Exception as e:
            print(f"FATAL ERROR: Invalid JSON in --config-json argument: {e}", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)

    elif args.extract_components:
        # Handle component extraction
        if args.file:
            # Process single file
            result = extract_components_from_file(args.file)
            print(json.dumps(result, indent=2))
            return result
        
        elif args.files:
            # Process multiple files
            results = extract_components_from_files(args.files)
            print(json.dumps(results, indent=2))
            return results
        
        else:
            print("Error: --extract-components requires either --file or --files argument")
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
    # main() # We keep the original main function for CLI usage

    # --- EXAMPLE: How to use the new simplified function ---
    #
    # To run this, you would uncomment the following lines and
    # replace the placeholder values with your actual repository
    # path and commit hashes.
    
    # import os
    #
    # print("\n--- RUNNING EXAMPLE: Simplified Diff for Two Commits ---")
    #
    # # 1. Define your repository path and commit hashes
    # my_repo_path = os.getcwd() # Or provide a specific path like "/path/to/your/repo"
    # older_commit = "PASTE_OLDER_COMMIT_HASH"
    # newer_commit = "PASTE_NEWER_COMMIT_HASH"
    #
    # # 2. Call the function
    # if "PASTE" not in older_commit and "PASTE" not in newer_commit:
    #      generate_ast_diff_for_commits(
    #          from_commit=older_commit,
    #          to_commit=newer_commit,
    #          repo_path=my_repo_path
    #      )
    # else:
    #      print("Please update the placeholder commit hashes in the script to run the example.")

    # The original main function is called to preserve command-line functionality
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
