from codetraverse.utils.AstDifferOrchestrator import *
import subprocess
import sys
import os
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import json


def fetch_commit_details(repo_path, commit_hash):
    """
    Fetches details for a single commit by shelling out to git.
    This function is designed to be called by a thread pool executor.

    Args:
        repo_path (str): The path to the repository.
        commit_hash (str): The hash of the commit to fetch.

    Returns:
        tuple: A tuple containing the commit hash and a dictionary of its details.
               Returns (None, None) if processing fails.
    """
    # A unique delimiter to safely split the git output.
    delimiter = "<--GIT-LOG-DELIMITER-->"
    command = [
        'git', 'show', '--quiet',
        # Format: Hash, Author, Date, Subject, Body. Delimiter is used between fields.
        f'--format=%H{delimiter}%an <%ae>{delimiter}%ad{delimiter}%s%n%b',
        '--date=iso-strict',  # Use a strict ISO format for easy parsing
        commit_hash
    ]
    try:
        commit_details_raw = subprocess.check_output(
            command,
            cwd=repo_path,
            text=True,
            stderr=subprocess.PIPE
        ).strip()
        
        # Split the output by the delimiter. We expect 4 parts.
        parts = commit_details_raw.split(delimiter, 3)
        if len(parts) == 4:
            chash, author, date, message = parts
            return chash, {
                "author": author.strip(),
                "date": date.strip(),
                "commit_message": message.strip()
            }
    except subprocess.CalledProcessError as e:
        # This can happen if the git command fails for a specific commit.
        print(f"Error processing commit {commit_hash}: {e.stderr}", file=sys.stderr)
    
    return None, None


def get_git_commits(repo_path, branch_name, top_commits=None, max_workers=10):
    """
    Retrieves and returns a dictionary of git commits for a given branch
    in chronological order, using multiple threads for speed.

    Args:
        repo_path (str): The absolute or relative path to the local git repository.
        branch_name (str): The name of the branch to inspect.
        top_commits (int, optional): The number of latest commits to fetch. 
                                     If None, float('inf'), or > total commits, fetches all. Defaults to None.
        max_workers (int): The maximum number of threads to use.

    Returns:
        dict: An ordered dictionary (in Python 3.7+) where keys are commit hashes
              and values are dicts containing author, date, and commit message.
              The dictionary is ordered from the initial commit to the latest.
    """
    if not os.path.isdir(os.path.join(repo_path, '.git')):
        print(f"Error: '{repo_path}' is not a valid Git repository.", file=sys.stderr)
        sys.exit(1)

    try:
        # Check if the branch exists before proceeding.
        subprocess.run(
            ['git', 'rev-parse', '--verify', branch_name],
            cwd=repo_path, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError:
        print(f"Error: Branch '{branch_name}' not found in the repository.", file=sys.stderr)
        sys.exit(1)

    try:
        # Get the list of all commit hashes in reverse chronological order (newest to oldest).
        commit_hashes = subprocess.check_output(
            ['git', 'rev-list', branch_name],
            cwd=repo_path, text=True
        ).strip().split('\n')

        if not commit_hashes or not commit_hashes[0]:
            print(f"No commits found on branch '{branch_name}'.")
            return {}

        # If top_commits is specified, slice the list to get only the latest N commits.
        if top_commits is not None and top_commits != float('inf') and top_commits > 0:
            commit_hashes = commit_hashes[:top_commits]
        
        # Reverse the list of hashes to be in chronological order (oldest to newest) for processing.
        commit_hashes.reverse()

        # Dictionaries in Python 3.7+ preserve insertion order.
        commits_dict = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Use executor.map to process commits in parallel while preserving order.
            results_iterator = executor.map(fetch_commit_details, [repo_path] * len(commit_hashes), commit_hashes)
            
            # Use tqdm to show a progress bar.
            for commit_hash, details in tqdm(results_iterator, total=len(commit_hashes), desc="Processing commits"):
                if commit_hash and details:
                    commits_dict[commit_hash] = details
        
        # Save the chronologically ordered commits to a JSON file.
        output_filename = "commits_output.json"
        with open(output_filename, "w") as f:
            json.dump(commits_dict, f, indent=4)
        print(f"\nSuccessfully processed {len(commits_dict)} commits.")
        print(f"Output saved to {output_filename}")

        return commits_dict

    except subprocess.CalledProcessError as e:
        print(f"An error occurred while executing a git command: {e}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'git' command not found. Please ensure Git is installed and in your system's PATH.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    # This makes the script runnable from the command line.
    # Note: You may need to install tqdm (`pip install tqdm`).
    if len(sys.argv) not in [3, 4]:
        print("Usage: python <script_name>.py <path_to_repo> <branch_name> [top_commits]", file=sys.stderr)
        sys.exit(1)

    repo_path_arg = sys.argv[1]
    branch_name_arg = sys.argv[2]
    top_commits_arg = None

    if len(sys.argv) == 4:
        try:
            # Allow 'inf' to be passed for all commits, otherwise expect an integer.
            if sys.argv[3].lower() == 'inf':
                top_commits_arg = float('inf')
            else:
                top_commits_arg = int(sys.argv[3])
            
            if isinstance(top_commits_arg, int) and top_commits_arg <= 0:
                raise ValueError("top_commits must be a positive integer.")
        except ValueError as e:
            print(f"Error: Invalid value for top_commits. {e}", file=sys.stderr)
            sys.exit(1)
    
    commits = get_git_commits(repo_path_arg, branch_name_arg, top_commits=top_commits_arg)

    # To verify the order, we can print the first and last commits from the result.
    if commits:
        ordered_hashes = list(commits.keys())
        print("\n--- Verification (Chronological Order) ---")
        print("First commit in result (oldest fetched):")
        print(json.dumps(commits[ordered_hashes[0]], indent=2))
        
        if len(ordered_hashes) > 1:
            print("\nLast commit in result (newest fetched):")
            print(json.dumps(commits[ordered_hashes[-1]], indent=2))