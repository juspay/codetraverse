import * as fs from 'fs';
import simpleGit, { SimpleGit } from 'simple-git';
import * as unidiff from 'unidiff';

export class GitWrapper {
    private git: SimpleGit;

    constructor(private repoPath: string) {
        if (!fs.existsSync(repoPath)) {
            throw new Error(`Repository path does not exist: ${repoPath}`);
        }
        this.git = simpleGit(repoPath);
    }

    async getLatestCommitFromBranch(branchName: string): Promise<string> {
        try {
            await this.git.fetch("origin", branchName);
        } catch (e: any) {
            console.warn(`Warning: Failed to fetch branch '${branchName}': ${e.message}`);
        }

        const fullRef = `origin/${branchName}`;
        try {
            const log = await this.git.log([fullRef, '-n', '1']);
            return log.latest!.hash;
        } catch (e) {
            const log = await this.git.log([branchName, '-n', '1']);
            return log.latest!.hash;
        }
    }

    async getCommonAncestor(branch1: string, branch2: string): Promise<string> {
        try {
            await this.git.fetch("origin", branch1);
            await this.git.fetch("origin", branch2);
        } catch (e: any) {
            console.warn(`Warning: fetch failed: ${e.message}`);
        }

        const ref1 = `origin/${branch1}`;
        const ref2 = `origin/${branch2}`;
        const mergeBase = await this.git.raw('merge-base', ref1, ref2);
        return mergeBase.trim();
    }

    async getChangedFilesFromCommits(toCommit: string, fromCommit: string): Promise<{ added: string[], deleted: string[], modified: string[] }> {
        const diff = await this.git.diffSummary([fromCommit, toCommit]);
        const changes = {
            added: diff.files.filter(f => f.binary === false && f.changes === f.insertions && f.deletions === 0).map(f => f.file),
            deleted: diff.files.filter(f => f.binary === false && f.changes === f.deletions && f.insertions === 0).map(f => f.file),
            modified: diff.files.filter(f => f.binary === false && f.insertions > 0 && f.deletions > 0).map(f => f.file),
        };
        return changes;
    }

    async getChangedFilesFromCommitsRaw(fromCommit: string, toCommit: string): Promise<string> {
        return this.git.diff([fromCommit, toCommit]);
    }

    async getStructuredDiff(fromCommit: string, toCommit: string): Promise<{ added: Record<string, [number, string][]>, removed: Record<string, [number, string][]> }> {
        const addedChanges: Record<string, [number, string][]> = {};
        const removedChanges: Record<string, [number, string][]> = {};

        const rawDiff = await this.git.diff([`${fromCommit}..${toCommit}`, '-U0']);
        const patch = (unidiff as any).default.parsePatch(rawDiff);

        for (const patchedFile of patch) {
            const filename = (patchedFile.newFileName || patchedFile.oldFileName).split('/').pop()!;
            for (const hunk of patchedFile.hunks) {
                for (const line of hunk.lines) {
                    if (line.type === 'add') {
                        if (!addedChanges[filename]) {
                            addedChanges[filename] = [];
                        }
                        addedChanges[filename].push([line.ln, line.text]);
                    } else if (line.type === 'del') {
                        if (!removedChanges[filename]) {
                            removedChanges[filename] = [];
                        }
                        removedChanges[filename].push([line.ln, line.text]);
                    }
                }
            }
        }
        return { added: addedChanges, removed: removedChanges };
    }

    async getFileContent(filePath: string, commit: string = "HEAD"): Promise<string> {
        try {
            return await this.git.show(`${commit}:${filePath}`);
        } catch (e: any) {
            throw new Error(`File '${filePath}' not found at commit '${commit}'. Error: ${e.message}`);
        }
    }
}
