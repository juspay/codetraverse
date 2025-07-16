import math
from codetraverse.GADA.gada_traverse import *

repo_path = "/Users/pradeesh.s/Documents/euler-api-txns"
branch_name = "staging"
# commits_data = get_git_commits(repo_path=repo_path, branch_name=branch_name, max_workers=32)


config = { 
    "provider_type": "local",                                                                                          
    "local": { "repo_path": repo_path },
    "from_commit": "b4e55b5ed2ffff820cd283fc5c67a5692f7f22ae",
    "to_commit": "718af94dc6dbfe8b08303b6c55c21f8448741bc6",
    "quiet": True,
    "save_as_json":True
    }
def get_functions_from_ast_diff(ast_diff):
    res_funcs = set()
    for chunk in ast_diff:
        keys = ["addedFunctions", "modifiedFunctions", "deletedFunctions"]
        
        curr_mod = chunk.get("moduleName", "UNK")
        for key in keys:
            for func_details in chunk.get(key, []):
                curr_func = func_details[0]
                curr_key = curr_func + "--" + curr_mod
                res_funcs.add(curr_key)
    return list(res_funcs)

# res = run_ast_diff_from_config(config=config)
# print(get_functions_from_ast_diff(res))

def process_commit_pair(repo_path, from_commit, to_commit):
    try:
        config = {
            "provider_type": "local",
            "local": {"repo_path": repo_path},
            "from_commit": from_commit,
            "to_commit": to_commit,
            "quiet": True,
            "save_as_json": False
        }
        ast_diff_result = run_ast_diff_from_config(config=config)
        diff_data = get_functions_from_ast_diff(ast_diff_result)
        result_value = diff_data
        
        return to_commit, result_value
        
    except Exception as e:
        print(f"Error processing pair {from_commit[:7]} -> {to_commit[:7]}: {e}")
        return None, None


def get_git_data(repo_path, branch_name, top_commits=None, max_workers=32):

    commits_data = get_git_commits(repo_path=repo_path, branch_name=branch_name, max_workers=max_workers, top_commits=top_commits)
    
    if not commits_data or len(commits_data) < 2:
        print("\nNot enough commits to generate diffs. Need at least 2.")
        return {}
    commits_keys = list(commits_data.keys())
    from_commits = commits_keys[:-1]
    to_commits = commits_keys[1:]
    
    all_results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        repo_paths = [repo_path] * len(from_commits)
        results_iterator = executor.map(process_commit_pair, repo_paths, from_commits, to_commits)
        
        print("\nStarting diff generation...")
        for key, value in tqdm(results_iterator, total=len(from_commits), desc="Generating diffs"):
            if key and value:
                all_results[key] = value

    output_filename = "git_data.json"
    with open(output_filename, "w") as f:
        json.dump(all_results, f, indent=4)
    print(f"\nSuccessfully generated diff data for {len(all_results)} commit pairs.")
    print(f"Diff data saved to {output_filename}")
    
    return all_results


get_git_data(repo_path=repo_path, branch_name=branch_name, top_commits=50)