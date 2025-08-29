import axios, { AxiosRequestConfig, AxiosResponse } from 'axios';

async function handleResponse<T>(response: AxiosResponse, processor: (res: AxiosResponse) => T): Promise<T | null> {
    if (response.status === 200) {
        try {
            return processor(response);
        } catch (e) {
            console.error("Error: Failed to parse JSON response.");
            return null;
        }
    }
    console.error(`Error: Received status code ${response.status}`);
    console.error(response.data);
    return null;
}

export class BitBucket {
    private baseUrl: string;
    private projectKey: string;
    private repoSlug: string;
    private auth: any;
    private headers: any;

    private FILE_CONTENT_URL: string;
    private GET_PR_URL: string;
    private GET_LATEST_COMMIT_URL: string;
    private DIFF_URL: string;
    private DIFF_URL_RAW: string;
    private GET_PRS_URL: string;

    constructor(options: { base_url: string, project_key: string, repo_slug: string, auth: any, headers?: any }) {
        this.baseUrl = options.base_url;
        this.projectKey = options.project_key;
        this.repoSlug = options.repo_slug;
        this.auth = options.auth;
        this.headers = options.headers || { 'Accept': 'application/json' };

        this.FILE_CONTENT_URL = `${this.baseUrl}/api/latest/projects/${this.projectKey}/repos/${this.repoSlug}/browse/{path}`;
        this.GET_PR_URL = `${this.baseUrl}/api/latest/projects/${this.projectKey}/repos/${this.repoSlug}/pull-requests/{pullRequestId}`;
        this.GET_LATEST_COMMIT_URL = `${this.baseUrl}/api/latest/projects/${this.projectKey}/repos/${this.repoSlug}/commits/{branchName}?limit=1`;
        this.DIFF_URL = `${this.baseUrl}/api/latest/projects/${this.projectKey}/repos/${this.repoSlug}/compare/diff`;
        this.DIFF_URL_RAW = `${this.baseUrl}/api/latest/projects/${this.projectKey}/repos/${this.repoSlug}/diff`;
        this.GET_PRS_URL = `${this.baseUrl}/api/latest/projects/${this.projectKey}/repos/${this.repoSlug}/pull-requests?state=OPEN&at=refs/heads/{sourceBranch}&direction=OUTGOING`;
    }

    private getFilePathFromObject(json_object: any): string {
        if (json_object.parent === "") {
            return json_object.name;
        }
        return `${json_object.parent}/${json_object.name}`;
    }

    async getChangedFilesFromCommits(fromCommit: string, toCommit: string): Promise<{ added: string[], deleted: string[], modified: string[] } | null> {
        const discoverFiles = (response: AxiosResponse) => {
            const jsonData = response.data;
            const changes = { added: [], deleted: [], modified: [] };
            for (const diff of jsonData.diffs || []) {
                if (!diff.source) {
                    changes.added.push(this.getFilePathFromObject(diff.destination));
                } else if (!diff.destination) {
                    changes.deleted.push(this.getFilePathFromObject(diff.source));
                } else {
                    changes.modified.push(this.getFilePathFromObject(diff.source));
                }
            }
            return changes;
        };

        const finalUrl = this.DIFF_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug);
        const params = { to: toCommit, from: fromCommit };
        const config: AxiosRequestConfig = { auth: this.auth, headers: this.headers, params };
        const response = await axios.get(finalUrl, config);
        return handleResponse(response, discoverFiles);
    }

    async getChangedFilesFromCommitsRaw(fromCommit: string, toCommit: string): Promise<string | null> {
        const finalUrl = this.DIFF_URL_RAW.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug);
        const params = { to: toCommit, from: fromCommit };
        const config: AxiosRequestConfig = { auth: this.auth, headers: this.headers, params };
        const response = await axios.get(finalUrl, config);
        return handleResponse(response, res => res.data);
    }

    async getPrBitbucket(prId: string): Promise<any | null> {
        const finalUrl = this.GET_PR_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug).replace('{pullRequestId}', prId);
        const config: AxiosRequestConfig = { auth: this.auth, headers: this.headers };
        const response = await axios.get(finalUrl, config);
        return handleResponse(response, res => res.data);
    }

    async getLatestCommitFromBranch(branchName: string): Promise<string | null> {
        const handleCommitResponse = (response: AxiosResponse) => response.data.id;
        const finalUrl = this.GET_LATEST_COMMIT_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug).replace('{branchName}', branchName);
        const config: AxiosRequestConfig = { auth: this.auth, headers: this.headers };
        const response = await axios.get(finalUrl, config);
        return handleResponse(response, handleCommitResponse);
    }

    async getPrId(branchName: string): Promise<[string, string, string] | null> {
        const handlePrResponse = (response: AxiosResponse): [string, string, string] | null => {
            const formattedResponse = response.data;
            for (const pr of formattedResponse.values || []) {
                if (pr.fromRef.displayId === branchName) {
                    return [pr.id, pr.fromRef.latestCommit, pr.toRef.latestCommit];
                }
            }
            return null;
        };
        const finalUrl = this.GET_PRS_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug).replace('{sourceBranch}', branchName);
        const config: AxiosRequestConfig = { auth: this.auth, headers: this.headers };
        const response = await axios.get(finalUrl, config);
        return handleResponse(response, handlePrResponse);
    }

    async getFileContent(filePath: string, commit: string = ""): Promise<string | null> {
        const handleFileResponse = (response: AxiosResponse) => {
            const formattedResponse = response.data;
            return (formattedResponse.lines || []).map((line: any) => line.text).join('\n');
        };
        const finalUrl = this.FILE_CONTENT_URL.replace('{projectKey}', this.projectKey).replace('{repositorySlug}', this.repoSlug).replace('{path}', filePath);
        const params = { at: commit, limit: 10000 };
        const config: AxiosRequestConfig = { auth: this.auth, headers: this.headers, params };
        const response = await axios.get(finalUrl, config);
        return handleResponse(response, handleFileResponse);
    }
}
