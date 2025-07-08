from git import Repo
from unidiff import PatchSet
import os
from typing import Dict, List, Optional, Tuple

class GitWrapper:
    def __init__(self, repo_path: str):
        if not os.path.exists(repo_path):
            raise ValueError(f"Repository path does not exist: {repo_path}")
        self.repo = Repo(repo_path)
        if self.repo.bare:
            raise ValueError(f"Repository at {repo_path} is bare or invalid.")

    def get_latest_commit_from_branch(self, branch_name: str) -> str:
        """Fetch remote branch and get latest commit hash"""
        # Try fetching explicitly to ensure remote is updated
        try:
            self.repo.git.fetch("origin", branch_name)
        except Exception as e:
            print(f"Warning: Failed to fetch branch '{branch_name}': {e}")

        # Prefer origin/<branch> if available
        full_ref = f"origin/{branch_name}"
        try:
            return self.repo.commit(full_ref).hexsha
        except Exception:
            # Fallback to local branch
            return self.repo.commit(branch_name).hexsha
        
    def get_common_ancestor(self, branch1: str, branch2: str) -> str:
        """Get the merge-base (common ancestor) of two branches"""
        try:
            self.repo.git.fetch("origin", branch1)
            self.repo.git.fetch("origin", branch2)
        except Exception as e:
            print(f"Warning: fetch failed: {e}")

        ref1 = f"origin/{branch1}"
        ref2 = f"origin/{branch2}"
        return self.repo.git.merge_base(ref1, ref2).strip()

    def get_changed_files_from_commits(self, to_commit: str, from_commit: str) -> Dict[str, List[str]]:
        """Get categorized list of changed files between two commits"""
        diff_index = self.repo.commit(from_commit).diff(to_commit, create_patch=False)
        changes = {
            "added": [],
            "deleted": [],
            "modified": []
        }

        for diff in diff_index:
            if diff.new_file:
                changes["added"].append(diff.b_path)
            elif diff.deleted_file:
                changes["deleted"].append(diff.a_path)
            else:
                changes["modified"].append(diff.a_path)
        return changes

    def get_changed_files_from_commits_raw(self, from_commit: str, to_commit: str) -> str:
        """Get raw git diff between two commits"""
        return self.repo.git.diff(from_commit, to_commit)
    
    def get_structured_diff(self, from_commit: str, to_commit: str) -> Tuple[dict, dict]:
        """Parse Git diff into structured added/removed changes with line numbers"""
        added_changes = {}
        removed_changes = {}

        raw_diff = self.repo.git.diff(from_commit, to_commit, unified=0)
        patch = PatchSet(raw_diff)

        for patched_file in patch:
            filename = patched_file.path.split("/")[-1]
            for hunk in patched_file:
                for line in hunk:
                    if line.is_added:
                        added_changes.setdefault(filename, []).append((line.target_line_no, line.value.rstrip()))
                    elif line.is_removed:
                        removed_changes.setdefault(filename, []).append((line.source_line_no, line.value.rstrip()))

        return added_changes, removed_changes

    def get_file_content(self, file_path: str, commit: Optional[str] = "HEAD") -> str:
        """Get the content of a file at a specific commit"""
        try:
            return self.repo.git.show(f"{commit}:{file_path}")
        except Exception as e:
            raise FileNotFoundError(f"File '{file_path}' not found at commit '{commit}'. Error: {str(e)}")
