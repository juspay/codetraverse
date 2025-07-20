import matplotlib.pyplot as plt
from codetraverse.GADA.gada_traverse import *
from codetraverse.GADA.gada_bayes import *
from concurrent.futures import ProcessPoolExecutor
from matplotlib.ticker import MaxNLocator

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
        keys = ["addedFunctions", "modifiedFunctions"] #"deletedFunctions"
        
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
    """
    Fetches git commits and generates diffs between them using a ProcessPoolExecutor.
    """
    # This part remains the same
    commits_data = get_git_commits(repo_path=repo_path, branch_name=branch_name, max_workers=max_workers, top_commits=top_commits)
    
    if not commits_data or len(commits_data) < 2:
        print("\nNot enough commits to generate diffs. Need at least 2.")
        return {}
        
    commits_keys = list(commits_data.keys())
    from_commits = commits_keys[:-1]
    to_commits = commits_keys[1:]
    
    all_results = {}

    # --- KEY CHANGE: Using ProcessPoolExecutor instead of ThreadPoolExecutor ---
    # ProcessPoolExecutor is ideal for CPU-bound tasks, as it bypasses Python's
    # Global Interpreter Lock (GIL) by using separate processes. This is useful
    # if process_commit_pair does heavy data processing in Python.
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        repo_paths = [repo_path] * len(from_commits)
        
        # The executor.map interface works identically for both pools
        results_iterator = executor.map(process_commit_pair, repo_paths, from_commits, to_commits)
        
        print("\nStarting diff generation with ProcessPoolExecutor...")
        for key, value in tqdm(results_iterator, total=len(from_commits), desc="Generating diffs"):
            if key and value:
                all_results[key] = value

    output_filename = "git_data_processes.json"
    with open(output_filename, "w") as f:
        json.dump(all_results, f, indent=4)
        
    print(f"\nSuccessfully generated diff data for {len(all_results)} commit pairs.")
    print(f"Diff data saved to {output_filename}")
    
    return all_results

def plot_probability_trends(
    prediction_probs: list, 
    path_probs: list, 
    commit_counts: list | None = None
):
    """
    Generates and displays a line graph showing the trend of probabilities
    and the number of supporting commits.

    Args:
        prediction_probs: A list of probabilities for each individual prediction step.
        path_probs: A list of the cumulative path probabilities at each step.
        commit_counts: A list of the number of commits supporting each prediction.
    """
    if not prediction_probs or not path_probs:
        print("Error: Cannot plot empty probability lists.")
        return

    try:
        fig, ax = plt.subplots(figsize=(14, 8))
        steps = range(1, len(prediction_probs) + 1)

        # --- Primary Y-axis (Probabilities) ---
        ax.set_xlabel("Prediction Step", fontsize=12)
        ax.set_ylabel("Probability", fontsize=12, color='#007ACC')
        ax.plot(steps, prediction_probs, marker='o', linestyle='--', color='#007ACC', label='Individual Step Probability')
        ax.plot(steps, path_probs, marker='s', linestyle='-', color='#D95319', label='Cumulative Path Probability')
        ax.set_ylim(0, 1.05)
        ax.tick_params(axis='y', labelcolor='#007ACC')
        ax.grid(True, which='major', axis='y', linestyle='--', linewidth=0.5)


        # --- Secondary Y-axis (Commit Counts) ---
        if commit_counts:
            ax2 = ax.twinx()  # Instantiate a second axes that shares the same x-axis
            ax2.set_ylabel('Number of Supporting Commits (Evidence)', color='#2ca02c', fontsize=12)
            ax2.plot(steps, commit_counts, marker='d', linestyle=':', color='#2ca02c', label='Supporting Commits Count')
            ax2.tick_params(axis='y', labelcolor='#2ca02c')
            # Ensure y-axis for counts has integer ticks
            ax2.yaxis.set_major_locator(MaxNLocator(integer=True))

        ax.set_title("Probability & Evidence Trends During Path Prediction", fontsize=16, fontweight='bold')
        ax.set_xticks(steps)
        
        # Combine legends from both axes
        lines, labels = ax.get_legend_handles_labels()
        if commit_counts:
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines + lines2, labels + labels2, loc='best')
        else:
            ax.legend(loc='best')

        fig.tight_layout()  # Adjust layout to make room for the new y-axis label
        plt.show()

    except Exception as e:
        print(f"An error occurred during plotting: {e}")


if __name__ == "__main__":

    # commit_data = get_git_data(repo_path=repo_path, branch_name=branch_name, top_commits=5000, max_workers=32)
    with open("git_data.json", "r") as f:
        commit_data = json.loads(f.read())
    with open("commits_output.json", "r") as f:
        commits_raw = json.loads(f.read())

    given = ["extractWebhookResponse--euler-x/src-generated/Gateway/Razorpay/Flow.hs", "parseRefundWebhookResponse--euler-x/src-generated/Gateway/EaseBuzz/Types.hs"]
    SUPPORT_COMMITS = []
    SUPPORT_PROB = []
    PATH_PROB = []
    # pair_freq, individual_freq = create_frequency_tables(commit_data=commit_data)
    # with open("pair_freq.json", "w") as f:
    #     json.dump(pair_freq, f)
    # with open("ind_freq.json", "w") as f:
    #     json.dump(individual_freq, f)
    index = create_inverted_index(commit_data=commit_data)

    def get_next_probable_func(og_given, given, commit_data, depth):
        
        most_probable, relevant_commits = find_most_probable_function_from_index(given, index)
        # most_probable = find_most_probable_functions(existing_functions=given, pair_frequencies=pair_freq, individual_frequencies=individual_freq)
        # most_probable = find_next_most_probable_function(conditional_functions=given, commit_data=commit_data)
        # relevant_commits = find_commits_with_functions(prior_functions=given, commit_data=commit_data)
        SUPPORT_COMMITS.append(len(relevant_commits))
        if most_probable:
            SUPPORT_PROB.append(most_probable[0][1])
            given.append(most_probable[0][0])
            curr_path_prob = calculate_path_probability(prior_functions=og_given, path_to_evaluate=given[len(og_given):], inverted_index=index)
            PATH_PROB.append(curr_path_prob)

        print(depth)
        if not most_probable or depth >= 10:
            relevant_commits = find_commits_with_functions(prior_functions=given, commit_data=commit_data)
            print("\n".join(og_given))
            print("-> ", end="")
            print(" \n-> ".join(given[len(og_given):]))
            if relevant_commits:
                print("\nFound matching commit(s):", len(relevant_commits))
                for commit_hash in relevant_commits[:5]:
                    print(f"- {commit_hash}, {commits_raw.get(commit_hash, {}).get("commit_message", "UNK").split("\n")[0]}, {commits_raw.get(commit_hash, {}).get("date", "UNK")}")
            return
        
        
        get_next_probable_func(og_given=og_given, given=given, commit_data=commit_data, depth=depth+1)

    get_next_probable_func(og_given=given.copy(), given=given, commit_data=commit_data, depth=1)
    print(SUPPORT_PROB)
    print(PATH_PROB)
    plot_probability_trends(prediction_probs=SUPPORT_PROB, path_probs=PATH_PROB, commit_counts=SUPPORT_COMMITS)