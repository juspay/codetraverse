"use strict";
var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.createFdepData = createFdepData;
var fs = require("fs");
var path = require("path");
var haskell_extractor_1 = require("./extractors/haskell_extractor");
var typescript_extractor_1 = require("./extractors/typescript_extractor");
var jsnetworkx_graph_1 = require("./utils/jsnetworkx_graph");
var haskell_adapter_1 = require("./adapters/haskell_adapter");
// import { adaptPythonComponents } from "./adapters/python_adapter";
// import { adaptRescriptComponents } from "./adapters/rescript_adapter";
// import { adaptRustComponents } from "./adapters/rust_adapter";
// import { adaptGoComponents } from "./adapters/go_adapter";
var typescript_adapter_1 = require("./adapters/typescript_adapter");
// Import the load function from utils
function loadComponentsWithoutHash(fdepDir) {
    var components = [];
    function walkDir(dir) {
        if (!fs.existsSync(dir)) {
            console.error("Directory does not exist: ".concat(dir));
            return;
        }
        var entries = fs.readdirSync(dir);
        for (var _i = 0, entries_1 = entries; _i < entries_1.length; _i++) {
            var entry = entries_1[_i];
            var fullPath = path.join(dir, entry);
            var stat = fs.statSync(fullPath);
            if (stat.isDirectory()) {
                walkDir(fullPath);
            }
            else if (path.extname(fullPath) === ".json") {
                try {
                    var data = JSON.parse(fs.readFileSync(fullPath, "utf-8"));
                    if (Array.isArray(data)) {
                        components.push.apply(components, data);
                    }
                    else {
                        components.push(data);
                    }
                }
                catch (e) {
                    console.error("Error reading file ".concat(fullPath, ":"), e.message);
                }
            }
        }
    }
    walkDir(fdepDir);
    return components;
}
var adapterMap = {
    "haskell": haskell_adapter_1.adaptHaskellComponents,
    // "python": adaptPythonComponents,
    // "rescript": adaptRescriptComponents,
    // "rust": adaptRustComponents,
    // "golang": adaptGoComponents,
    "typescript": typescript_adapter_1.adaptTypeScriptComponents
    // "purescript": adaptPurescriptComponents,
    // "javascript": adaptJavascriptComponents
};
var EXT_MAP = {
    "haskell": [".hs", ".lhs", ".hs-boot"],
    "python": [".py"],
    "rescript": [".res"],
    "golang": [".go"],
    "rust": [".rs"],
    "typescript": [".ts", ".tsx"],
    "purescript": [".purs"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"]
};
var INVERSE_EXTS = {};
for (var lang in EXT_MAP) {
    for (var _i = 0, _a = EXT_MAP[lang]; _i < _a.length; _i++) {
        var ext = _a[_i];
        INVERSE_EXTS[ext] = lang;
    }
}
function combineSchemas(old, newSchema) {
    return {
        nodes: old.nodes.concat(newSchema.nodes),
        edges: old.edges.concat(newSchema.edges)
    };
}
function getExtractor(language) {
    switch (language) {
        case "haskell":
            return new haskell_extractor_1.HaskellComponentExtractor();
        case "typescript":
            return new typescript_extractor_1.TypeScriptComponentExtractor();
        // case "python":
        //     return new PythonComponentExtractor();
        // Add other extractors here as they are implemented
        default:
            console.log("No extractor found for language: ".concat(language, ". Skipping it."));
            return undefined;
    }
}
function _processSingleFileWorker(args) {
    var codePath = args[0], languageStr = args[1], rootDirPath = args[2], outputBasePath = args[3];
    try {
        var extractorInstance = getExtractor(languageStr);
        if (extractorInstance) {
            extractorInstance.processFile(codePath);
            var relPath = path.relative(rootDirPath, codePath);
            var jsonRel = path.join(path.dirname(relPath), path.basename(relPath, path.extname(relPath))) + ".json";
            var outPath = path.join(outputBasePath, jsonRel);
            fs.mkdirSync(path.dirname(outPath), { recursive: true });
            extractorInstance.writeToFile(outPath);
        }
    }
    catch (e) {
        console.error(e.stack);
        console.error("Unable to process - ".concat(codePath, ". Skipping it."));
    }
}
function createFdepData(rootDir, outputBase, graphDir, clearExisting, skipAdaptor) {
    if (outputBase === void 0) { outputBase = "./output/fdep"; }
    if (graphDir === void 0) { graphDir = "./output/graph"; }
    if (clearExisting === void 0) { clearExisting = true; }
    if (skipAdaptor === void 0) { skipAdaptor = false; }
    process.env.ROOT_DIR = rootDir;
    var rootDirPath = path.resolve(rootDir);
    var languageFileMap = {};
    var gitignorePath = path.join(rootDirPath, ".gitignore");
    var gitignorePattern = fs.existsSync(gitignorePath) ? fs.readFileSync(gitignorePath, "utf-8").split("\n") : [];
    function isIgnored(filePath, patterns) {
        for (var _i = 0, patterns_1 = patterns; _i < patterns_1.length; _i++) {
            var pattern = patterns_1[_i];
            if (pattern.trim() === "" || pattern.startsWith("#")) {
                continue; // Skip empty lines and comments
            }
            if (pattern.startsWith("!")) {
                var cleanPattern = pattern.substring(1);
                if (matchesGitignorePattern(filePath, cleanPattern)) {
                    return false;
                }
            }
            else {
                if (matchesGitignorePattern(filePath, pattern)) {
                    return true;
                }
            }
        }
        return false;
    }
    function matchesGitignorePattern(filePath, pattern) {
        // Convert gitignore glob pattern to regex
        var regexPattern = pattern
            .replace(/\./g, '\\.') // Escape dots
            .replace(/\*/g, '.*') // Convert * to .*
            .replace(/\?/g, '.') // Convert ? to .
            .replace(/\//g, '\\/'); // Escape forward slashes
        // If pattern ends with /, it only matches directories
        if (pattern.endsWith('/')) {
            regexPattern = regexPattern.slice(0, -2) + '$'; // Remove the escaped / and anchor to end
            return new RegExp(regexPattern).test(filePath + '/');
        }
        // If pattern doesn't start with /, it can match at any level
        if (!pattern.startsWith('/')) {
            regexPattern = '(^|/)' + regexPattern;
        }
        regexPattern = '^' + regexPattern + '($|/)';
        try {
            return new RegExp(regexPattern).test(filePath);
        }
        catch (e) {
            // If regex is invalid, fall back to simple string matching
            return filePath.includes(pattern.replace(/[*?]/g, ''));
        }
    }
    function walk(dir) {
        var _a;
        var files = fs.readdirSync(dir);
        for (var _i = 0, files_1 = files; _i < files_1.length; _i++) {
            var file = files_1[_i];
            var fullPath = path.join(dir, file);
            var relativePath = path.relative(rootDirPath, fullPath);
            var ignored = isIgnored(relativePath, gitignorePattern);
            // Debug: log first few files
            if (((_a = languageFileMap.haskell) === null || _a === void 0 ? void 0 : _a.length) < 5 || path.extname(fullPath) === '.hs') {
                console.log("File: ".concat(relativePath, ", ignored: ").concat(ignored, ", ext: ").concat(path.extname(fullPath)));
            }
            if (ignored) {
                continue;
            }
            if (fs.statSync(fullPath).isDirectory()) {
                walk(fullPath);
            }
            else {
                var language = INVERSE_EXTS[path.extname(fullPath)];
                if (language) {
                    if (!languageFileMap[language]) {
                        languageFileMap[language] = [];
                    }
                    languageFileMap[language].push(fullPath);
                }
            }
        }
    }
    walk(rootDirPath);
    // Debug: Print language file map
    var languageFileCounts = Object.entries(languageFileMap).map(function (_a) {
        var lang = _a[0], files = _a[1];
        return "".concat(lang, ": ").concat(files.length, " files");
    });
    console.log("Language file map:", languageFileCounts);
    if (fs.existsSync(outputBase) && clearExisting) {
        fs.rmSync(outputBase, { recursive: true, force: true });
    }
    if (fs.existsSync(graphDir) && clearExisting) {
        fs.rmSync(graphDir, { recursive: true, force: true });
    }
    fs.mkdirSync(outputBase, { recursive: true });
    fs.mkdirSync(graphDir, { recursive: true });
    var _loop_1 = function (language) {
        console.log("Processing ".concat(languageFileMap[language].length, " ").concat(language, " files..."));
        try {
            var tasksArgs = languageFileMap[language].map(function (codePath) { return [codePath, language, rootDirPath, outputBase]; });
            tasksArgs.forEach(_processSingleFileWorker);
        }
        catch (e) {
            console.error(e.stack);
            console.error("ERROR -", e);
        }
    };
    for (var language in languageFileMap) {
        _loop_1(language);
    }
    console.log("Done! All outputs in: ".concat(outputBase));
    if (skipAdaptor) {
        return;
    }
    createGraph(outputBase, graphDir);
}
function createGraph(fdepDir, graphDir) {
    var rawFuncs = loadComponentsWithoutHash(fdepDir);
    var langCompDict = {};
    var countUnprocessableFunction = 0;
    for (var _i = 0, rawFuncs_1 = rawFuncs; _i < rawFuncs_1.length; _i++) {
        var func = rawFuncs_1[_i];
        try {
            var compLanguage = INVERSE_EXTS[path.extname(func.filePath || "")];
            if (compLanguage) {
                if (!langCompDict[compLanguage]) {
                    langCompDict[compLanguage] = [];
                }
                langCompDict[compLanguage].push(func);
            }
        }
        catch (e) {
            countUnprocessableFunction++;
        }
    }
    console.log("Total unprocessable functions: ".concat(countUnprocessableFunction));
    var unsupportedLanguages = Object.keys(langCompDict).filter(function (lang) { return !adapterMap[lang]; });
    if (unsupportedLanguages.length > 0) {
        console.log("Skipping unsupported languages: ".concat(unsupportedLanguages));
    }
    var filteredLangCompDict = Object.fromEntries(Object.entries(langCompDict).filter(function (_a) {
        var lang = _a[0];
        return adapterMap[lang];
    }));
    if (Object.keys(filteredLangCompDict).length === 0) {
        console.log("No supported languages found with components.");
        return;
    }
    var schemas = Object.entries(filteredLangCompDict)
        .map(function (_a) {
        var language = _a[0], comps = _a[1];
        return adapterMap[language](comps);
    });
    var unifiedSchema = schemas.reduce(combineSchemas, { nodes: [], edges: [] });
    var G = (0, jsnetworkx_graph_1.buildGraphFromSchema)(unifiedSchema);
    var graphGp = path.join(graphDir, "repo_function_calls.json");
    // Write graph data as JSON since jsnetworkx doesn't support GraphML
    var graphData = {
        nodes: G.nodes(true).map(function (_a) {
            var node = _a[0], attrs = _a[1];
            return (__assign({ id: node }, attrs));
        }),
        edges: G.edges(true).map(function (_a) {
            var u = _a[0], v = _a[1], attrs = _a[2];
            return (__assign({ from: u, to: v }, attrs));
        }),
    };
    fs.writeFileSync(graphGp, JSON.stringify(graphData, null, 2));
    console.log("Wrote graph data to ".concat(graphGp));
}
function main() {
    var args = process.argv.slice(2);
    if (args.length === 0) {
        console.error("Usage: node main.js <function> <arguments>");
        console.error("Available functions:");
        console.error("  create_fdep_data <root_dir> [output_base] [graph_dir] [clear_existing]");
        return;
    }
    var functionName = args[0];
    if (functionName === "create_fdep_data") {
        var rootDir = args[1];
        if (!rootDir) {
            console.error("Please provide a root directory.");
            return;
        }
        var outputBase = args[2] || "./output/fdep";
        var graphDir = args[3] || "./output/graph";
        var clearExisting = args[4] !== "false";
        console.log("Creating FDEP data from: ".concat(rootDir));
        console.log("Output base: ".concat(outputBase));
        console.log("Graph directory: ".concat(graphDir));
        console.log("Clear existing: ".concat(clearExisting));
        createFdepData(rootDir, outputBase, graphDir, clearExisting);
    }
    else {
        console.error("Unknown function: ".concat(functionName));
    }
}
if (require.main === module) {
    main();
}
