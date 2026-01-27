import os
import requests
import secrets
import hashlib
import logging
import urllib.parse
import time
from typing import Tuple, Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Setup Logger
logger = logging.getLogger(__name__)

class BitBucketError(Exception):
    """Custom exception for BitBucket Client errors to allow specific catching."""
    pass

class BitBucket:
    def __init__(self, base_url: str, project_key: str, repo_slug: str, auth: Tuple[str, str], headers: Dict = None):
        self.base_url = base_url.rstrip("/") + "/" if base_url else "https://bitbucket.juspay.net/rest/"
        self.project_key = project_key
        self.repo_slug = repo_slug
        self.auth = auth
        
        # Define API Templates
        self.api_base = self.base_url + "api/latest/projects/{projectKey}/repos/{repositorySlug}"
        self.FILE_CONTENT_URL = self.api_base + "/browse/{path}"
        self.GET_PR_URL = self.api_base + "/pull-requests/{pullRequestId}"
        self.GET_LATEST_COMMIT = self.api_base + "/commits"
        self.DIFF_URL = self.api_base + "/compare/diff"
        self.COMPARE_COMMITS = self.api_base + "/compare/commits"

        # Initialize Session with Retries
        self.session = self._init_robust_session(headers)
        
        logger.info(f"BitBucket Client initialized. Project: {project_key}, Repo: {repo_slug}")

    def _init_robust_session(self, headers: Optional[Dict]) -> requests.Session:
        """
        Creates a requests Session with automatic retries and backoff.
        This handles 429 (Rate Limit), 500, 502, 503, 504.
        """
        session = requests.Session()
        session.auth = self.auth
        
        # Merge custom headers including the dynamic User-Agent
        default_headers = self._generate_dynamic_headers(headers or {})
        session.headers.update(default_headers)

        # Retry Strategy: Wait 1s, 2s, 4s... up to 5 times.
        # 'status_forcelist' triggers retries on these specific codes.
        retry_strategy = Retry(
            total=5,
            backoff_factor=1, 
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"] # Only retry safe methods
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session

    def _generate_dynamic_headers(self, headers: Dict) -> Dict:
        """Generates headers with a randomized User-Agent to help avoid static blocking."""
        ua_secret = os.getenv("USER_AGENT_SECRET", "ResearchAgent")
        random_nonce = secrets.token_hex(8) 
        data_to_hash = f"{ua_secret}{random_nonce}"
        signature = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
        
        custom_user_agent = f"gitdiff-service/{random_nonce}/{signature}"
        
        headers["Accept"] = "application/json;charset=UTF-8"
        headers["User-Agent"] = custom_user_agent
        return headers

    def _get_url(self, template: str, **kwargs) -> str:
        """Safely constructs the URL with encoding."""
        safe_kwargs = {k: urllib.parse.quote(str(v), safe='') for k, v in kwargs.items()}
        
        # Always inject Project and Repo
        safe_kwargs['projectKey'] = urllib.parse.quote(self.project_key, safe='')
        safe_kwargs['repositorySlug'] = urllib.parse.quote(self.repo_slug, safe='')
        
        # Handle path specifically to allow slashes
        if "{path}" in template and "path" in kwargs:
            safe_kwargs['path'] = urllib.parse.quote(kwargs['path']) 
            
        return template.format(**safe_kwargs)

    def _make_request(self, method: str, url: str, params: Dict = None, allow_404: bool = False) -> Any:
        try:
            # 1. Set a strict timeout
            response = self.session.request(method, url, params=params, timeout=30)

            # 2. Handle 404 Gracefully if allowed
            if response.status_code == 404 and allow_404:
                logger.warning(f"404 Not Found for {url}. Returning None as requested.")
                return None

            # 3. Critical Failure Logging (403 Forbidden)
            if response.status_code == 403:
                logger.critical(f"CRITICAL: 403 Forbidden at {url}. Check Rate Limits or Permissions.")

            # 4. Standard Error Raising
            response.raise_for_status()

            # 5. Return JSON or Text
            if "application/json" in response.headers.get("Content-Type", ""):
                return response.json()
            return response.text

        except requests.exceptions.RetryError:
            logger.error(f"Max retries exceeded for {url}")
            raise BitBucketError(f"Max retries exceeded connecting to BitBucket.")
        except requests.exceptions.HTTPError as e:
            # Re-check 404 in case raise_for_status caught it before our check (order matters above)
            if response.status_code == 404 and allow_404:
                return None
            logger.error(f"HTTP Error {e.response.status_code} for {url}: {e.response.text}")
            raise BitBucketError(f"BitBucket API failed: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Network Error connecting to {url}: {str(e)}")
            raise BitBucketError(f"Network failure: {e}")
        except ValueError:
            logger.error(f"Invalid JSON received from {url}")
            raise BitBucketError("Failed to parse JSON response")

    def get_file_path_from_object(self, json_object: Dict) -> str:
        if not json_object:
            return ""
        parent = json_object.get("parent", "")
        name = json_object.get("name", "")
        if not parent:
            return name
        return f"{parent}/{name}"

    def get_changed_files_from_commits(self, from_commit: str, to_commit: str) -> Dict[str, list]:
        final_url = self._get_url(self.DIFF_URL)
        params = {"to": to_commit, "from": from_commit, "limit": 1000} # Increased limit
        
        logger.debug(f"Fetching diff files {from_commit} -> {to_commit}")
        
        data = self._make_request("GET", final_url, params=params)
        
        changes = {"added": [], "deleted": [], "modified": []}
        for diff in data.get("diffs", []):
            if diff.get("source") is None:
                changes["added"].append(self.get_file_path_from_object(diff["destination"]))
            elif diff.get("destination") is None:
                changes["deleted"].append(self.get_file_path_from_object(diff["source"]))
            else:
                changes["modified"].append(self.get_file_path_from_object(diff["source"]))
        return changes

    def get_structured_diff(self, from_commit: str, to_commit: str) -> Tuple[Dict, Dict]:
        final_url = self._get_url(self.DIFF_URL)
        params = {"to": to_commit, "from": from_commit, "contextLines": 0, "limit": 1000}
        
        data = self._make_request("GET", final_url, params=params)
        
        added_changes = {}
        removed_changes = {}

        for diff in data.get("diffs", []):
            path_obj = diff.get("destination") or diff.get("source")
            if not path_obj:
                continue
            
            full_path = self.get_file_path_from_object(path_obj)
            filename = full_path.split("/")[-1]

            for hunk in diff.get("hunks", []):
                for segment in hunk.get("segments", []):
                    lines = segment.get("lines", [])
                    if segment["type"] == "ADDED":
                        for line in lines:
                            added_changes.setdefault(filename, []).append((line.get("destination"), line.get("line", "").rstrip()))
                    elif segment["type"] == "REMOVED":
                        for line in lines:
                            removed_changes.setdefault(filename, []).append((line.get("source"), line.get("line", "").rstrip()))
                            
        return added_changes, removed_changes

    def get_pr_bitbucket(self, pr_id: str) -> Dict:
        final_url = self._get_url(self.GET_PR_URL, pullRequestId=pr_id)
        logger.info(f"Fetching PR #{pr_id}")
        return self._make_request("GET", final_url)

    def get_latest_commit_from_branch(self, branch_name: str) -> str:
        # Use 'until' parameter for commits api to filter by branch
        final_url = self._get_url(self.GET_LATEST_COMMIT)
        params = {"until": branch_name, "limit": 1}
        
        data = self._make_request("GET", final_url, params=params)
        
        if "values" in data and len(data["values"]) > 0:
            return data["values"][0]["id"]
            
        raise BitBucketError(f"No commits found for branch {branch_name}")

    def get_pr_merge_base(self, source_ref: str, target_ref: str) -> str:
        final_url = self._get_url(self.COMPARE_COMMITS)
        # BitBucket REST API usually expects 'from' as source and 'to' as target for comparison
        # However, for merge-base, we want the common ancestor
        params = {
            "from": target_ref, 
            "to": source_ref,
            "withCounts": "true"
        }
        
        logger.info(f"Calculating merge-base: {target_ref} -> {source_ref}")
        data = self._make_request("GET", final_url, params=params)
        
        common_ancestor = data.get("commonAncestor")
        if not common_ancestor or "id" not in common_ancestor:
            raise BitBucketError(f"Merge-base not found for {target_ref} -> {source_ref}")
            
        return common_ancestor["id"]

    def get_file_content(self, file_path: str, commit: str = "") -> Optional[str]:
            final_url = self._get_url(self.FILE_CONTENT_URL, path=file_path)
            params = {"limit": 10000}
            if commit:
                params["at"] = commit
                
            data = self._make_request("GET", final_url, params=params, allow_404=True)
            
            if data is None:
                return None

            if isinstance(data, dict) and "lines" in data:
                return "\n".join(line.get("text", "") for line in data["lines"])
            
            return str(data)