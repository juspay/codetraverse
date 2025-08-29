declare module 'unidiff' {
    export interface HunkLine {
        type: 'add' | 'del' | 'cntx';
        ln: number;
        ln2: number;
        text: string;
    }

    export interface Hunk {
        lines: HunkLine[];
    }

    export interface PatchedFile {
        from: string;
        to: string;
        hunks: Hunk[];
    }

    export function parse(diff: string): PatchedFile[];
}
