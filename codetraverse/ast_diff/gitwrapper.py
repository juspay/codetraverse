import os
import logging
from git import Repo, GitCommandError
from unidiff import PatchSet
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class GitWrapperError(Exception):
    """Custom exception for Git Wrapper errors."""
    pass

class GitWrapper:
    def __init__(self, repo_path: str):
        if not os.path.exists(repo_path):
            raise GitWrapperError(f"Repository path does not exist: {repo_path}")
        
        try:
            self.repo = Repo(repo_path)
            if self.repo.bare:
                raise GitWrapperError(f"Repository at {repo_path} is bare or invalid.")
        except Exception as e:
            raise GitWrapperError(f"Failed to initialize Git repo at {repo_path}: {e}")
            
        logger.info(f"Git Client initialized for Repo: {repo_path}")

    def get_latest_commit_from_branch(self, branch_name: str) -> str:
        """
        Fetch remote branch and get latest commit hash.
        Robust strategy: Try 'origin/<branch>', fallback to local '<branch>'.
        """
        # 1. Attempt to fetch (Best Effort)
        try:
            self.repo.git.fetch("origin", branch_name)
        except GitCommandError as e:
            logger.warning(f"Could not fetch origin/{branch_name}: {e}. relying on local refs.")

        # 2. Try Remote Ref (Preferred)
        remote_ref = f"origin/{branch_name}"
        try:
            return self.repo.commit(remote_ref).hexsha
        except (ValueError, GitCommandError):
            pass 
        
        # 3. Fallback to Local Ref
        try:
            return self.repo.commit(branch_name).hexsha
        except (ValueError, GitCommandError):
            raise GitWrapperError(f"Could not find commit for branch '{branch_name}' locally or on origin.")

    def get_common_ancestor(self, target_ref: str, source_ref: str) -> str:
        """
        Get the merge-base (common ancestor) of two refs.
        Resolves branches automatically to their SHAs.
        """
        def resolve_sha(ref):
            # If it's already a SHA, return it
            if len(ref) == 40 and all(c in '0123456789abcdef' for c in ref.lower()):
                return ref
            # Try origin/ref then local ref
            try:
                return self.repo.commit(f"origin/{ref}").hexsha
            except:
                try:
                    return self.repo.commit(ref).hexsha
                except:
                    raise GitWrapperError(f"Could not resolve reference: {ref}")

        sha1 = resolve_sha(target_ref)
        sha2 = resolve_sha(source_ref)
        
        try:
            # git merge-base <commit1> <commit2>
            return self.repo.git.merge_base(sha1, sha2).strip()
        except GitCommandError as e:
            raise GitWrapperError(f"Failed to find merge-base for {target_ref} and {source_ref}: {e}")

    def get_changed_files_from_commits(self, from_commit: str, to_commit: str) -> Dict[str, List[str]]:
        """
        Get categorized list of changed files between two commits.
        Matches Bitbucket JSON structure: {'added': [], 'deleted': [], 'modified': []}
        """
        changes = {"added": [], "deleted": [], "modified": []}
        
        try:
            # Diff index: from -> to
            diff_index = self.repo.commit(from_commit).diff(to_commit)
            
            for diff in diff_index:
                # GitPython Diff Objects:
                # new_file: True if added
                # deleted_file: True if deleted
                # renamed_file: True if renamed
                
                if diff.new_file:
                    changes["added"].append(diff.b_path)
                elif diff.deleted_file:
                    changes["deleted"].append(diff.a_path)
                elif diff.renamed_file:
                    # Treat rename as Modified (most diff tools do this)
                    # You could also treat as Added(b_path) + Deleted(a_path) if preferred
                    changes["modified"].append(diff.b_path)
                else:
                    changes["modified"].append(diff.a_path)
                    
            return changes
        except Exception as e:
            raise GitWrapperError(f"Failed to diff commits {from_commit} -> {to_commit}: {e}")

    def get_file_content(self, file_path: str, commit: str) -> Optional[str]:
        """
        Get content of a file. Returns None if file does not exist (Critical for diff logic).
        """
        try:
            # equivalent to `git show commit:path`
            return self.repo.git.show(f"{commit}:{file_path}")
        except GitCommandError as e:
            err_msg = str(e).lower()
            # Check for standard git "not found" errors
            if "exists on disk, but not in" in err_msg or "does not exist" in err_msg or "path" in err_msg:
                return None
            
            logger.error(f"Git error fetching {file_path} at {commit}: {e}")
            raise GitWrapperError(f"Failed to read file {file_path}")

    def get_structured_diff(self, from_commit: str, to_commit: str) -> Tuple[dict, dict]:
        """
        Parse Git diff into structured added/removed changes with line numbers.
        Safe against binary files or weird encodings.
        """
        added_changes = {}
        removed_changes = {}

        try:
            # unified=0 for minimal context
            raw_diff = self.repo.git.diff(from_commit, to_commit, unified=0)
            
            # If diff is empty (no changes), return empty dicts
            if not raw_diff:
                return {}, {}

            patch = PatchSet(raw_diff)

            for patched_file in patch:
                filename = patched_file.path
                # Handle /dev/null for adds/deletes
                if patched_file.is_added_file:
                    filename = patched_file.path # b_path
                elif patched_file.is_removed_file:
                    filename = patched_file.path # a_path
                
                # Strip leading "a/" or "b/" if PatchSet includes them (it usually handles this, but be safe)
                if filename.startswith("a/") or filename.startswith("b/"):
                    filename = filename[2:]

                for hunk in patched_file:
                    for line in hunk:
                        if line.is_added:
                            added_changes.setdefault(filename, []).append((line.target_line_no, line.value.rstrip()))
                        elif line.is_removed:
                            removed_changes.setdefault(filename, []).append((line.source_line_no, line.value.rstrip()))
                            
            return added_changes, removed_changes
            
        except Exception as e:
            logger.error(f"Failed to parse structured diff {from_commit}->{to_commit}: {e}")
            raise GitWrapperError("Failed to generate structured diff")