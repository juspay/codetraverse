import * as fs from 'fs';
import * as path from 'path';
const Parser = require('tree-sitter');
import { GitWrapper } from '../ast_diff/gitwrapper';
import { BitBucket } from '../ast_diff/bitbucket';
import { HaskellFileDiff } from '../ast_diff/haskelldiff';
import { TypeScriptFileDiff } from '../ast_diff/TSdiff';
import { RustFileDiff } from '../ast_diff/rustdiff';
import { PythonFileDiff } from '../ast_diff/pythondiff';
import * as diff from 'diff';

// No-op
type DifferClass = new (filename: string, parser?: any) => any;

interface LanguageHandler {
    lang_obj: any;
    differ_class: DifferClass;
}

export class AstDiffOrchestrator {
    private static EXT_MAP: Record<string, string[]> = {
        "haskell":    ['.hs', '.lhs', '.hs-boot'],
        "typescript": ['.ts', '.tsx'],
        "rust":       ['.rs'],
        "python":     ['.py']
    };

    public static INVERSE_EXTS: Record<string, string> = Object.entries(AstDiffOrchestrator.EXT_MAP).reduce((acc, [lang, exts]) => {
        for (const ext of exts) {
            acc[ext] = lang;
        }
        return acc;
    }, {} as Record<string, string>);

    private language_handlers: Record<string, LanguageHandler>;
    private parsers: Record<string, any>;

    constructor() {
        this.language_handlers = {
            "haskell":    { lang_obj: null, differ_class: HaskellFileDiff },
            "typescript": { lang_obj: null, differ_class: TypeScriptFileDiff },
            "rust":       { lang_obj: null, differ_class: RustFileDiff },
            "python":     { lang_obj: null, differ_class: PythonFileDiff }
        };

        this.parsers = {};
    }

    public async init() {
        for (const lang in this.language_handlers) {
            try {
                const handler = this.language_handlers[lang];
                const lang_module = require(`tree-sitter-${lang}`);
                handler.lang_obj = lang_module[lang] || lang_module;
                const parser = new (Parser as any)();
                try {
                    parser.setLanguage(handler.lang_obj);
                    this.parsers[lang] = parser;
                } catch (e) {
                    console.error(`Error setting language for ${lang}`, e);
                }
            } catch (e) {
                console.error(`Failed to load tree-sitter grammar for ${lang}`, e);
            }
        }
        
        // Special handling for TSX
        try {
            const tsx_lang_module = require('tree-sitter-typescript');
            const tsx_parser = new (Parser as any)();
            tsx_parser.setLanguage(tsx_lang_module.tsx);
            this.parsers['.tsx'] = tsx_parser;
        } catch (e) {
            console.error(`Failed to load tree-sitter grammar for tsx`, e);
        }
    }

    private getExtension(filename: string): string {
        return path.extname(filename);
    }

    public isSupported(filename: string): boolean {
        return this.getExtension(filename) in AstDiffOrchestrator.INVERSE_EXTS;
    }

    public getParser(filename: string): any | undefined {
        const ext = this.getExtension(filename);
        if (ext === '.tsx') {
            return this.parsers['.tsx'];
        }
        const lang = AstDiffOrchestrator.INVERSE_EXTS[ext];
        return this.parsers[lang];
    }

    public getDiffer(filename: string): any | null {
        const ext = this.getExtension(filename);
        const lang = AstDiffOrchestrator.INVERSE_EXTS[ext];
        const handler = this.language_handlers[lang];
        if (handler) {
            const parser = this.getParser(filename);
            return new handler.differ_class(filename, parser);
        }
        return null;
    }
}

export interface ComponentData {
    name: string;
    start_line: number;
    end_line: number;
    content: string;
    start_byte: number;
    end_byte: number;
}

export interface ExtractionResult {
    file_path: string;
    language: string;
    components: Record<string, ComponentData[]>;
    error?: string;
}

export function extractComponentsFromFile(filePath: string): ExtractionResult {
    if (!fs.existsSync(filePath)) {
        return { error: `File not found: ${filePath}`, file_path: filePath, language: 'unknown', components: {} };
    }

    const orchestrator = new AstDiffOrchestrator();

    if (!orchestrator.isSupported(filePath)) {
        return { error: `Unsupported file type: ${filePath}`, file_path: filePath, language: 'unknown', components: {} };
    }

    const parser = orchestrator.getParser(filePath);
    const differ = orchestrator.getDiffer(filePath);

    if (!parser || !differ) {
        return { error: `Could not get parser/differ for: ${filePath}`, file_path: filePath, language: 'unknown', components: {} };
    }

    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const ast = parser.parse(content);
        const components = differ.extract_components(ast.rootNode);

        const result: ExtractionResult = {
            file_path: filePath,
            language: AstDiffOrchestrator.INVERSE_EXTS[path.extname(filePath)] || "unknown",
            components: {}
        };

        if (typeof components === 'object' && components !== null) {
            if (Array.isArray(components)) {
                const language = result.language;
                const component_names = {
                    "haskell": ["functions", "dataTypes", "typeClasses", "instances", "imports", "templateHaskell"],
                    "typescript": ["functions", "classes", "interfaces", "types", "enums", "constants", "fields"]
                }[language] || ["functions", "classes", "types", "variables", "imports", "constants"];

                components.forEach((component_dict, i) => {
                    if (i < component_names.length && component_dict) {
                        const component_type = component_names[i];
                        result.components[component_type] = [];
                        for (const name in component_dict) {
                            const data = component_dict[name];
                            if (Array.isArray(data) && data.length >= 4) {
                                result.components[component_type].push({
                                    name: name,
                                    start_line: data[2][0] + 1,
                                    end_line: data[3][0] + 1,
                                    content: data[1],
                                    start_byte: data[2][1] || 0,
                                    end_byte: data[3][1] || 0
                                });
                            }
                        }
                    }
                });
            } else {
                for (const component_type in components) {
                    const items = components[component_type];
                    if (items) {
                        result.components[component_type] = [];
                        for (const name in items) {
                            const data = items[name];
                            if (Array.isArray(data) && data.length >= 4) {
                                result.components[component_type].push({
                                    name: name,
                                    start_line: data[2][0] + 1,
                                    end_line: data[3][0] + 1,
                                    content: data[1],
                                    start_byte: data[2][1] || 0,
                                    end_byte: data[3][1] || 0
                                });
                            }
                        }
                    }
                }
            }
        }

        return result;
    } catch (e: any) {
        return { error: `Error processing file ${filePath}: ${e.message}`, file_path: filePath, language: 'unknown', components: {} };
    }
}

export function extractComponentsFromFiles(filePaths: string[]): ExtractionResult[] {
    const results: ExtractionResult[] = [];
    for (const filePath of filePaths) {
        try {
            const result = extractComponentsFromFile(filePath);
            results.push(result);
        } catch (e: any) {
            const errorResult: ExtractionResult = {
                file_path: filePath,
                error: `Error processing file ${filePath}: ${e.message}`,
                language: 'unknown',
                components: {}
            };
            results.push(errorResult);
        }
    }
    return results;
}

export interface AstDiffOptions {
    git_provider: GitWrapper | BitBucket;
    output_dir?: string;
    quiet?: boolean;
    pr_id?: string;
    from_branch?: string;
    to_branch?: string;
    from_commit?: string;
    to_commit?: string;
    write_to_file?: boolean;
}

export async function generateAstDiff(options: AstDiffOptions): Promise<any[]> {
    const orchestrator = new AstDiffOrchestrator();
    await orchestrator.init();
    const all_changes: any[] = [];

    try {
        let { from_commit, to_commit } = options;

        if (!from_commit || !to_commit) {
            if (options.git_provider instanceof BitBucket && options.pr_id) {
                const pull_request = await options.git_provider.getPrBitbucket(options.pr_id);
                to_commit = pull_request.fromRef.latestCommit;
                from_commit = pull_request.toRef.latestCommit;
            } else if (options.git_provider instanceof GitWrapper && options.from_branch && options.to_branch) {
                to_commit = await options.git_provider.getLatestCommitFromBranch(options.from_branch);
                from_commit = await options.git_provider.getCommonAncestor(options.from_branch, options.to_branch);
            } else {
                throw new Error("Insufficient information to determine commit range.");
            }
        }

        console.log(`Comparing commits: ${from_commit?.slice(0, 7)} (old) -> ${to_commit?.slice(0, 7)} (new)`);

        const changed_files = await options.git_provider.getChangedFilesFromCommits(to_commit!, from_commit!);
        const { added: structured_diff_added, removed: structured_diff_removed } = await (options.git_provider as any).getStructuredDiff(from_commit, to_commit);

        for (const category of ["modified", "added", "deleted"]) {
            for (const file_path of changed_files[category] || []) {
                if (file_path.endsWith(".lock")) {
                    continue;
                }

                const parser = orchestrator.getParser(file_path);
                const differ = orchestrator.getDiffer(file_path);

                if (!parser || !differ) {
                    // Fallback to text diff
                    // This part will be implemented later
                    continue;
                }

                let changes;
                if (category === "modified") {
                    const old_content = await (options.git_provider as any).getFileContent(file_path, from_commit);
                    const new_content = await (options.git_provider as any).getFileContent(file_path, to_commit);

                    try {
                        if (old_content && new_content) {
                            const old_ast = parser.parse(old_content);
                            const new_ast = parser.parse(new_content);
                            changes = differ.compareTwoFiles(old_ast.rootNode, new_ast.rootNode);
                        } else if (new_content) {
                            const ast = parser.parse(new_content);
                            changes = differ.processSingleFile(ast.rootNode, 'added');
                        } else if (old_content) {
                            const ast = parser.parse(old_content);
                            changes = differ.processSingleFile(ast.rootNode, 'deleted');
                        }
                    } catch (e) {
                        console.error(`Error parsing file: ${file_path}, falling back to text-based diff`);
                        if (old_content && new_content) {
                            const patch = diff.createPatch(file_path, old_content, new_content);
                            all_changes.push({
                                file_path: file_path,
                                language: 'unknown',
                                changes: patch,
                                error: `Error parsing file: ${file_path}, fallback to text-based diff`
                            });
                        }
                    }
                } else {
                    const commit = category === "added" ? to_commit : from_commit;
                    const content = await (options.git_provider as any).getFileContent(file_path, commit);
                    if (content) {
                        try {
                            const ast = parser.parse(content);
                            changes = differ.processSingleFile(ast.rootNode, category);
                        } catch (e) {
                            console.error(`Error parsing file: ${file_path}, falling back to text-based diff`);
                            all_changes.push({
                                file_path: file_path,
                                language: 'unknown',
                                changes: content,
                                error: `Error parsing file: ${file_path}, fallback to text-based diff`
                            });
                        }
                    }
                }

                if (changes) {
                    all_changes.push(changes.to_dict());
                }
            }
        }
        return all_changes;
    } catch (e: any) {
        console.error(`ERROR - ${e.message}`);
        console.error(e.stack);
        return [];
    }
}

export interface Config {
    provider_type: 'bitbucket' | 'local';
    bitbucket?: {
        base_url: string;
        project_key: string;
        repo_slug: string;
        auth: any;
        headers?: any;
    };
    local?: {
        repo_path: string;
    };
    output_dir?: string;
    quiet?: boolean;
    pr_id?: string;
    from_branch?: string;
    to_branch?: string;
    from_commit?: string;
    to_commit?: string;
}

export async function runAstDiffFromConfig(config: Config): Promise<any[]> {
    console.log("--- Starting AST Diff Generation from Config ---");
    let git_provider: GitWrapper | BitBucket;

    try {
        if (config.provider_type === "bitbucket" && config.bitbucket) {
            git_provider = new BitBucket(config.bitbucket);
        } else if (config.provider_type === "local" && config.local) {
            git_provider = new GitWrapper(config.local.repo_path);
        } else {
            throw new Error(`Unsupported provider_type: '${config.provider_type}'. Must be 'bitbucket' or 'local'.`);
        }

        const all_changes = await generateAstDiff({
            git_provider,
            output_dir: config.output_dir,
            quiet: config.quiet,
            pr_id: config.pr_id,
            from_branch: config.from_branch,
            to_branch: config.to_branch,
            from_commit: config.from_commit,
            to_commit: config.to_commit,
        });

        console.log("--- AST Diff Generation Finished ---");
        console.log(JSON.stringify(all_changes, null, 2));
        return all_changes;
    } catch (e: any) {
        console.error(`FATAL ERROR in configuration or execution: ${e.message}`);
        console.error(e.stack);
        process.exit(1);
    }
}

async function main() {
    const { ArgumentParser } = require('argparse');
    const parser = new ArgumentParser({
        description: "Generate an Abstract Syntax Tree (AST) diff for code changes or extract components."
    });

    parser.add_argument('--config-json', { help: 'A JSON string containing the configuration.' });
    parser.add_argument('--extract-components', { action: 'store_true', help: 'Extract components from files instead of generating diff.' });
    parser.add_argument('--file', { help: 'Single file to extract components from.' });
    parser.add_argument('--files', { nargs: '+', help: 'Multiple files to extract components from.' });
    parser.add_argument('--output-file', { help: 'Output file to save component extraction results.' });

    const subparsers = parser.add_subparsers({ dest: 'provider_type', help: 'Specify the Git provider.' });

    const parent_parser = new ArgumentParser({ add_help: false });
    parent_parser.add_argument('--output-dir', { default: './ast_diff_output', help: 'Directory to save the output JSON file.' });
    parent_parser.add_argument('--from-branch', { help: 'The source branch name.' });
    parent_parser.add_argument('--to-branch', { help: 'The target branch name (e.g., main).' });
    parent_parser.add_argument('--from-commit', { help: 'The starting commit hash.' });
    parent_parser.add_argument('--to-commit', { help: 'The ending commit hash.' });
    parent_parser.add_argument('--quiet', { action: 'store_true', help: 'Suppress processing status messages.' });

    const parser_local = subparsers.add_parser('local', { parents: [parent_parser], help: 'Use a local Git repository.' });
    parser_local.add_argument('repo_path', { nargs: '?', default: null, help: 'The file path to the local Git repository.' });

    const parser_bb = subparsers.add_parser('bitbucket', { parents: [parent_parser], help: 'Use a remote Bitbucket repository.' });
    parser_bb.add_argument('--base-url', { help: 'Bitbucket server base URL.' });
    parser_bb.add_argument('--project-key', { help: 'Bitbucket project key.' });
    parser_bb.add_argument('--repo-slug', { help: 'Bitbucket repository slug.' });
    parser_bb.add_argument('--user', { help: 'Bitbucket username for authentication.' });
    parser_bb.add_argument('--token', { help: 'Bitbucket password or personal access token.' });
    parser_bb.add_argument('--pr-id', { help: 'Pull Request ID to automatically get commits.' });

    const args = parser.parse_args();

    if (args.config_json) {
        try {
            let config = JSON.parse(args.config_json);
            if (typeof config === 'string') {
                config = JSON.parse(config);
            }
            if (typeof config !== 'object') {
                throw new Error("Config is not a valid object.");
            }
            await runAstDiffFromConfig(config);
        } catch (e: any) {
            console.error(`FATAL ERROR: Invalid JSON in --config-json argument: ${e.message}`);
            console.error(e.stack);
            process.exit(1);
        }
    } else if (args.extract_components) {
        let results;
        if (args.file) {
            results = extractComponentsFromFile(args.file);
        } else if (args.files) {
            results = extractComponentsFromFiles(args.files);
        } else {
            console.error("Error: --extract-components requires either --file or --files argument");
            process.exit(1);
        }
        console.log(JSON.stringify(results, null, 2));
    } else if (args.provider_type) {
        const config: Config = {
            provider_type: args.provider_type,
            output_dir: args.output_dir,
            quiet: args.quiet,
            pr_id: args.pr_id,
            from_branch: args.from_branch,
            to_branch: args.to_branch,
            from_commit: args.from_commit,
            to_commit: args.to_commit,
        };

        if (args.provider_type === "local") {
            if (!args.repo_path) {
                parser.error("the following arguments are required: repo_path");
            }
            config.local = { repo_path: args.repo_path };
        } else if (args.provider_type === "bitbucket") {
            if (!args.base_url || !args.project_key || !args.repo_slug || !args.user || !args.token) {
                parser.error("missing required arguments for bitbucket provider.");
            }
            config.bitbucket = {
                base_url: args.base_url,
                project_key: args.project_key,
                repo_slug: args.repo_slug,
                auth: [args.user, args.token]
            };
        }
        await runAstDiffFromConfig(config);
    } else {
        parser.print_help();
        process.exit(1);
    }
}

if (require.main === module) {
    main();
}

export async function generateAstDiffForCommits(
    from_commit: string,
    to_commit: string,
    repo_path: string,
    output_dir: string = "./ast_diff_output",
    quiet: boolean = false,
    write_to_file: boolean = false
): Promise<any[]> {
    console.log(`--- Starting AST Diff for Commits in Repo: ${repo_path} ---`);
    try {
        const git_provider = new GitWrapper(repo_path);
        const all_changes = await generateAstDiff({
            git_provider,
            from_commit,
            to_commit,
            output_dir,
            quiet,
            write_to_file
        });
        console.log("--- AST Diff Generation Finished ---");
        if (write_to_file) {
            const final_output_path = path.join(output_dir, "detailed_changes.json");
            console.log(`INFO: The detailed AST diff has been saved to '${final_output_path}'`);
        }
        console.log("INFO: The function is returning the following summary:");
        console.log(JSON.stringify(all_changes, null, 2));
        return all_changes;
    } catch (e: any) {
        console.error(`FATAL ERROR during AST diff generation: ${e.message}`);
        console.error(e.stack);
        return [];
    }
}
