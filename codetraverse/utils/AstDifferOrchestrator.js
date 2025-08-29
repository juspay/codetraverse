"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.AstDiffOrchestrator = void 0;
exports.extractComponentsFromFile = extractComponentsFromFile;
exports.extractComponentsFromFiles = extractComponentsFromFiles;
exports.generateAstDiff = generateAstDiff;
exports.runAstDiffFromConfig = runAstDiffFromConfig;
exports.generateAstDiffForCommits = generateAstDiffForCommits;
var fs = require("fs");
var path = require("path");
var Parser = require('tree-sitter');
var gitwrapper_1 = require("../ast_diff/gitwrapper");
var bitbucket_1 = require("../ast_diff/bitbucket");
var haskelldiff_1 = require("../ast_diff/haskelldiff");
var TSdiff_1 = require("../ast_diff/TSdiff");
var godiff_1 = require("../ast_diff/godiff");
var rustdiff_1 = require("../ast_diff/rustdiff");
var pythondiff_1 = require("../ast_diff/pythondiff");
// Assuming a similar mechanism to get languages as in python
var Haskell = require('tree-sitter-haskell');
var TypeScript = require('tree-sitter-typescript').typescript;
var TSX = require('tree-sitter-typescript').tsx;
var Go = require('tree-sitter-go');
var Rust = require('tree-sitter-rust');
var Python = require('tree-sitter-python');
var AstDiffOrchestrator = /** @class */ (function () {
    function AstDiffOrchestrator() {
        this.language_handlers = {
            "haskell": { lang_obj: Haskell, differ_class: haskelldiff_1.HaskellFileDiff },
            "typescript": { lang_obj: TypeScript, differ_class: TSdiff_1.TypeScriptFileDiff },
            "go": { lang_obj: Go, differ_class: godiff_1.GoFileDiff },
            "rust": { lang_obj: Rust, differ_class: rustdiff_1.RustFileDiff },
            "python": { lang_obj: Python, differ_class: pythondiff_1.PythonFileDiff }
        };
        this.parsers = {};
        for (var lang in this.language_handlers) {
            var handler = this.language_handlers[lang];
            var parser = new Parser();
            parser.setLanguage(handler.lang_obj);
            this.parsers[lang] = parser;
        }
        // Special handling for TSX
        var tsx_parser = new Parser();
        tsx_parser.setLanguage(TSX);
        this.parsers['.tsx'] = tsx_parser;
    }
    AstDiffOrchestrator.prototype.getExtension = function (filename) {
        return path.extname(filename);
    };
    AstDiffOrchestrator.prototype.isSupported = function (filename) {
        return this.getExtension(filename) in AstDiffOrchestrator.INVERSE_EXTS;
    };
    AstDiffOrchestrator.prototype.getParser = function (filename) {
        var ext = this.getExtension(filename);
        if (ext === '.tsx') {
            return this.parsers['.tsx'];
        }
        var lang = AstDiffOrchestrator.INVERSE_EXTS[ext];
        return this.parsers[lang];
    };
    AstDiffOrchestrator.prototype.getDiffer = function (filename) {
        var ext = this.getExtension(filename);
        var lang = AstDiffOrchestrator.INVERSE_EXTS[ext];
        var handler = this.language_handlers[lang];
        if (handler) {
            return new handler.differ_class(filename);
        }
        return null;
    };
    AstDiffOrchestrator.EXT_MAP = {
        "haskell": ['.hs', '.lhs', '.hs-boot'],
        "typescript": ['.ts', '.tsx'],
        "go": ['.go'],
        "rust": ['.rs'],
        "python": ['.py']
    };
    AstDiffOrchestrator.INVERSE_EXTS = Object.entries(AstDiffOrchestrator.EXT_MAP).reduce(function (acc, _a) {
        var lang = _a[0], exts = _a[1];
        for (var _i = 0, exts_1 = exts; _i < exts_1.length; _i++) {
            var ext = exts_1[_i];
            acc[ext] = lang;
        }
        return acc;
    }, {});
    return AstDiffOrchestrator;
}());
exports.AstDiffOrchestrator = AstDiffOrchestrator;
function extractComponentsFromFile(filePath) {
    if (!fs.existsSync(filePath)) {
        return { error: "File not found: ".concat(filePath), file_path: filePath, language: 'unknown', components: {} };
    }
    var orchestrator = new AstDiffOrchestrator();
    if (!orchestrator.isSupported(filePath)) {
        return { error: "Unsupported file type: ".concat(filePath), file_path: filePath, language: 'unknown', components: {} };
    }
    var parser = orchestrator.getParser(filePath);
    var differ = orchestrator.getDiffer(filePath);
    if (!parser || !differ) {
        return { error: "Could not get parser/differ for: ".concat(filePath), file_path: filePath, language: 'unknown', components: {} };
    }
    try {
        var content = fs.readFileSync(filePath, 'utf-8');
        var ast = parser.parse(content);
        var components = differ.extract_components(ast.rootNode);
        var result_1 = {
            file_path: filePath,
            language: AstDiffOrchestrator.INVERSE_EXTS[path.extname(filePath)] || "unknown",
            components: {}
        };
        if (typeof components === 'object' && components !== null) {
            if (Array.isArray(components)) {
                var language = result_1.language;
                var component_names_1 = {
                    "haskell": ["functions", "dataTypes", "typeClasses", "instances", "imports", "templateHaskell"],
                    "typescript": ["functions", "classes", "interfaces", "types", "enums", "constants", "fields"]
                }[language] || ["functions", "classes", "types", "variables", "imports", "constants"];
                components.forEach(function (component_dict, i) {
                    if (i < component_names_1.length && component_dict) {
                        var component_type = component_names_1[i];
                        result_1.components[component_type] = [];
                        for (var name_1 in component_dict) {
                            var data = component_dict[name_1];
                            if (Array.isArray(data) && data.length >= 4) {
                                result_1.components[component_type].push({
                                    name: name_1,
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
            }
            else {
                for (var component_type in components) {
                    var items = components[component_type];
                    if (items) {
                        result_1.components[component_type] = [];
                        for (var name_2 in items) {
                            var data = items[name_2];
                            if (Array.isArray(data) && data.length >= 4) {
                                result_1.components[component_type].push({
                                    name: name_2,
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
        return result_1;
    }
    catch (e) {
        return { error: "Error processing file ".concat(filePath, ": ").concat(e.message), file_path: filePath, language: 'unknown', components: {} };
    }
}
function extractComponentsFromFiles(filePaths) {
    var results = [];
    for (var _i = 0, filePaths_1 = filePaths; _i < filePaths_1.length; _i++) {
        var filePath = filePaths_1[_i];
        try {
            var result = extractComponentsFromFile(filePath);
            results.push(result);
        }
        catch (e) {
            var errorResult = {
                file_path: filePath,
                error: "Error processing file ".concat(filePath, ": ").concat(e.message),
                language: 'unknown',
                components: {}
            };
            results.push(errorResult);
        }
    }
    return results;
}
function generateAstDiff(options) {
    return __awaiter(this, void 0, void 0, function () {
        var orchestrator, all_changes, from_commit, to_commit, pull_request, changed_files, _a, structured_diff_added, structured_diff_removed, _i, _b, category, _c, _d, file_path, parser, differ, changes, old_content, new_content, old_ast, new_ast, ast, ast, commit, content, ast, e_1;
        return __generator(this, function (_e) {
            switch (_e.label) {
                case 0:
                    orchestrator = new AstDiffOrchestrator();
                    all_changes = [];
                    _e.label = 1;
                case 1:
                    _e.trys.push([1, 20, , 21]);
                    from_commit = options.from_commit, to_commit = options.to_commit;
                    if (!(!from_commit || !to_commit)) return [3 /*break*/, 7];
                    if (!(options.git_provider instanceof bitbucket_1.BitBucket && options.pr_id)) return [3 /*break*/, 3];
                    return [4 /*yield*/, options.git_provider.get_pr_bitbucket(options.pr_id)];
                case 2:
                    pull_request = _e.sent();
                    to_commit = pull_request.fromRef.latestCommit;
                    from_commit = pull_request.toRef.latestCommit;
                    return [3 /*break*/, 7];
                case 3:
                    if (!(options.git_provider instanceof gitwrapper_1.GitWrapper && options.from_branch && options.to_branch)) return [3 /*break*/, 6];
                    return [4 /*yield*/, options.git_provider.get_latest_commit_from_branch(options.from_branch)];
                case 4:
                    to_commit = _e.sent();
                    return [4 /*yield*/, options.git_provider.get_common_ancestor(options.from_branch, options.to_branch)];
                case 5:
                    from_commit = _e.sent();
                    return [3 /*break*/, 7];
                case 6: throw new Error("Insufficient information to determine commit range.");
                case 7:
                    console.log("Comparing commits: ".concat(from_commit === null || from_commit === void 0 ? void 0 : from_commit.slice(0, 7), " (old) -> ").concat(to_commit === null || to_commit === void 0 ? void 0 : to_commit.slice(0, 7), " (new)"));
                    return [4 /*yield*/, options.git_provider.get_changed_files_from_commits(to_commit, from_commit)];
                case 8:
                    changed_files = _e.sent();
                    return [4 /*yield*/, options.git_provider.get_structured_diff(from_commit, to_commit)];
                case 9:
                    _a = _e.sent(), structured_diff_added = _a.added, structured_diff_removed = _a.removed;
                    _i = 0, _b = ["modified", "added", "deleted"];
                    _e.label = 10;
                case 10:
                    if (!(_i < _b.length)) return [3 /*break*/, 19];
                    category = _b[_i];
                    _c = 0, _d = changed_files[category] || [];
                    _e.label = 11;
                case 11:
                    if (!(_c < _d.length)) return [3 /*break*/, 18];
                    file_path = _d[_c];
                    if (file_path.endsWith(".lock")) {
                        return [3 /*break*/, 17];
                    }
                    parser = orchestrator.getParser(file_path);
                    differ = orchestrator.getDiffer(file_path);
                    if (!parser || !differ) {
                        // Fallback to text diff
                        // This part will be implemented later
                        return [3 /*break*/, 17];
                    }
                    changes = void 0;
                    if (!(category === "modified")) return [3 /*break*/, 14];
                    return [4 /*yield*/, options.git_provider.get_file_content(file_path, from_commit)];
                case 12:
                    old_content = _e.sent();
                    return [4 /*yield*/, options.git_provider.get_file_content(file_path, to_commit)];
                case 13:
                    new_content = _e.sent();
                    if (old_content && new_content) {
                        old_ast = parser.parse(old_content);
                        new_ast = parser.parse(new_content);
                        changes = differ.compare_two_files(old_ast, new_ast);
                    }
                    else if (new_content) {
                        ast = parser.parse(new_content);
                        changes = differ.process_single_file(ast, 'added');
                    }
                    else if (old_content) {
                        ast = parser.parse(old_content);
                        changes = differ.process_single_file(ast, 'deleted');
                    }
                    return [3 /*break*/, 16];
                case 14:
                    commit = category === "added" ? to_commit : from_commit;
                    return [4 /*yield*/, options.git_provider.get_file_content(file_path, commit)];
                case 15:
                    content = _e.sent();
                    if (content) {
                        ast = parser.parse(content);
                        changes = differ.process_single_file(ast, category);
                    }
                    _e.label = 16;
                case 16:
                    if (changes) {
                        all_changes.push(changes.to_dict());
                    }
                    _e.label = 17;
                case 17:
                    _c++;
                    return [3 /*break*/, 11];
                case 18:
                    _i++;
                    return [3 /*break*/, 10];
                case 19: return [2 /*return*/, all_changes];
                case 20:
                    e_1 = _e.sent();
                    console.error("ERROR - ".concat(e_1.message));
                    console.error(e_1.stack);
                    return [2 /*return*/, []];
                case 21: return [2 /*return*/];
            }
        });
    });
}
function runAstDiffFromConfig(config) {
    return __awaiter(this, void 0, void 0, function () {
        var git_provider, all_changes, e_2;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    console.log("--- Starting AST Diff Generation from Config ---");
                    _a.label = 1;
                case 1:
                    _a.trys.push([1, 3, , 4]);
                    if (config.provider_type === "bitbucket" && config.bitbucket) {
                        git_provider = new bitbucket_1.BitBucket(config.bitbucket);
                    }
                    else if (config.provider_type === "local" && config.local) {
                        git_provider = new gitwrapper_1.GitWrapper(config.local.repo_path);
                    }
                    else {
                        throw new Error("Unsupported provider_type: '".concat(config.provider_type, "'. Must be 'bitbucket' or 'local'."));
                    }
                    return [4 /*yield*/, generateAstDiff({
                            git_provider: git_provider,
                            output_dir: config.output_dir,
                            quiet: config.quiet,
                            pr_id: config.pr_id,
                            from_branch: config.from_branch,
                            to_branch: config.to_branch,
                            from_commit: config.from_commit,
                            to_commit: config.to_commit,
                        })];
                case 2:
                    all_changes = _a.sent();
                    console.log("--- AST Diff Generation Finished ---");
                    console.log(JSON.stringify(all_changes, null, 2));
                    return [2 /*return*/, all_changes];
                case 3:
                    e_2 = _a.sent();
                    console.error("FATAL ERROR in configuration or execution: ".concat(e_2.message));
                    console.error(e_2.stack);
                    process.exit(1);
                    return [3 /*break*/, 4];
                case 4: return [2 /*return*/];
            }
        });
    });
}
function main() {
    return __awaiter(this, void 0, void 0, function () {
        var ArgumentParser, parser, subparsers, parent_parser, parser_local, parser_bb, args, config, e_3, results, config;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    ArgumentParser = require('argparse').ArgumentParser;
                    parser = new ArgumentParser({
                        description: "Generate an Abstract Syntax Tree (AST) diff for code changes or extract components."
                    });
                    parser.add_argument('--config-json', { help: 'A JSON string containing the configuration.' });
                    parser.add_argument('--extract-components', { action: 'store_true', help: 'Extract components from files instead of generating diff.' });
                    parser.add_argument('--file', { help: 'Single file to extract components from.' });
                    parser.add_argument('--files', { nargs: '+', help: 'Multiple files to extract components from.' });
                    parser.add_argument('--output-file', { help: 'Output file to save component extraction results.' });
                    subparsers = parser.add_subparsers({ dest: 'provider_type', help: 'Specify the Git provider.' });
                    parent_parser = new ArgumentParser({ add_help: false });
                    parent_parser.add_argument('--output-dir', { default: './ast_diff_output', help: 'Directory to save the output JSON file.' });
                    parent_parser.add_argument('--from-branch', { help: 'The source branch name.' });
                    parent_parser.add_argument('--to-branch', { help: 'The target branch name (e.g., main).' });
                    parent_parser.add_argument('--from-commit', { help: 'The starting commit hash.' });
                    parent_parser.add_argument('--to-commit', { help: 'The ending commit hash.' });
                    parent_parser.add_argument('--quiet', { action: 'store_true', help: 'Suppress processing status messages.' });
                    parser_local = subparsers.add_parser('local', { parents: [parent_parser], help: 'Use a local Git repository.' });
                    parser_local.add_argument('repo_path', { nargs: '?', default: null, help: 'The file path to the local Git repository.' });
                    parser_bb = subparsers.add_parser('bitbucket', { parents: [parent_parser], help: 'Use a remote Bitbucket repository.' });
                    parser_bb.add_argument('--base-url', { help: 'Bitbucket server base URL.' });
                    parser_bb.add_argument('--project-key', { help: 'Bitbucket project key.' });
                    parser_bb.add_argument('--repo-slug', { help: 'Bitbucket repository slug.' });
                    parser_bb.add_argument('--user', { help: 'Bitbucket username for authentication.' });
                    parser_bb.add_argument('--token', { help: 'Bitbucket password or personal access token.' });
                    parser_bb.add_argument('--pr-id', { help: 'Pull Request ID to automatically get commits.' });
                    args = parser.parse_args();
                    if (!args.config_json) return [3 /*break*/, 5];
                    _a.label = 1;
                case 1:
                    _a.trys.push([1, 3, , 4]);
                    config = JSON.parse(args.config_json);
                    if (typeof config === 'string') {
                        config = JSON.parse(config);
                    }
                    if (typeof config !== 'object') {
                        throw new Error("Config is not a valid object.");
                    }
                    return [4 /*yield*/, runAstDiffFromConfig(config)];
                case 2:
                    _a.sent();
                    return [3 /*break*/, 4];
                case 3:
                    e_3 = _a.sent();
                    console.error("FATAL ERROR: Invalid JSON in --config-json argument: ".concat(e_3.message));
                    console.error(e_3.stack);
                    process.exit(1);
                    return [3 /*break*/, 4];
                case 4: return [3 /*break*/, 9];
                case 5:
                    if (!args.extract_components) return [3 /*break*/, 6];
                    results = void 0;
                    if (args.file) {
                        results = extractComponentsFromFile(args.file);
                    }
                    else if (args.files) {
                        results = extractComponentsFromFiles(args.files);
                    }
                    else {
                        console.error("Error: --extract-components requires either --file or --files argument");
                        process.exit(1);
                    }
                    console.log(JSON.stringify(results, null, 2));
                    return [3 /*break*/, 9];
                case 6:
                    if (!args.provider_type) return [3 /*break*/, 8];
                    config = {
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
                    }
                    else if (args.provider_type === "bitbucket") {
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
                    return [4 /*yield*/, runAstDiffFromConfig(config)];
                case 7:
                    _a.sent();
                    return [3 /*break*/, 9];
                case 8:
                    parser.print_help();
                    process.exit(1);
                    _a.label = 9;
                case 9: return [2 /*return*/];
            }
        });
    });
}
if (require.main === module) {
    main();
}
function generateAstDiffForCommits(from_commit_1, to_commit_1, repo_path_1) {
    return __awaiter(this, arguments, void 0, function (from_commit, to_commit, repo_path, output_dir, quiet, write_to_file) {
        var git_provider, all_changes, final_output_path, e_4;
        if (output_dir === void 0) { output_dir = "./ast_diff_output"; }
        if (quiet === void 0) { quiet = false; }
        if (write_to_file === void 0) { write_to_file = false; }
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    console.log("--- Starting AST Diff for Commits in Repo: ".concat(repo_path, " ---"));
                    _a.label = 1;
                case 1:
                    _a.trys.push([1, 3, , 4]);
                    git_provider = new gitwrapper_1.GitWrapper(repo_path);
                    return [4 /*yield*/, generateAstDiff({
                            git_provider: git_provider,
                            from_commit: from_commit,
                            to_commit: to_commit,
                            output_dir: output_dir,
                            quiet: quiet,
                            write_to_file: write_to_file
                        })];
                case 2:
                    all_changes = _a.sent();
                    console.log("--- AST Diff Generation Finished ---");
                    if (write_to_file) {
                        final_output_path = path.join(output_dir, "detailed_changes.json");
                        console.log("INFO: The detailed AST diff has been saved to '".concat(final_output_path, "'"));
                    }
                    console.log("INFO: The function is returning the following summary:");
                    console.log(JSON.stringify(all_changes, null, 2));
                    return [2 /*return*/, all_changes];
                case 3:
                    e_4 = _a.sent();
                    console.error("FATAL ERROR during AST diff generation: ".concat(e_4.message));
                    console.error(e_4.stack);
                    return [2 /*return*/, []];
                case 4: return [2 /*return*/];
            }
        });
    });
}
