import * as fs from "fs";
import * as path from "path";
import * as jsnx from "jsnetworkx";
import { buildGraphFromSchema } from "./utils/jsnetworkx_graph";
import { adaptHaskellComponents } from "./adapters/haskell_adapter";
import { adaptPythonComponents } from "./adapters/python_adapter";
import { getExtractor } from "./registry/extractor_registry";
// import { adaptRescriptComponents } from "./adapters/rescript_adapter";
import { adaptRustComponents } from "./adapters/rust_adapter";
import { adaptGoComponents } from "./adapters/go_adapter";
import { adaptTypeScriptComponents } from "./adapters/typescript_adapter";
// import { adaptPurescriptComponents } from "./adapters/purescript_adapter";
import { adaptJavascriptComponents } from "./adapters/javascript_adapter";
import { Component } from "./types/types";
import ignore from "ignore";

function loadGitIgnore(baseDir: string): ignore.Ignore {
    const gitignorePath = path.join(baseDir, ".gitignore");
    const ig = ignore();

    if (fs.existsSync(gitignorePath)) {
        const content = fs.readFileSync(gitignorePath, "utf8");
        ig.add(content.split(/\r?\n/));
    }

    return ig;
}

// Import the load function from utils
function loadComponentsWithoutHash(fdepDir: string): Component[] {
    const components: Component[] = [];
    
    function walkDir(dir: string) {
        if (!fs.existsSync(dir)) {
            console.error(`Directory does not exist: ${dir}`);
            return;
        }
        
        const entries = fs.readdirSync(dir);
        for (const entry of entries) {
            const fullPath = path.join(dir, entry);
            const stat = fs.statSync(fullPath);
            
            if (stat.isDirectory()) {
                walkDir(fullPath);
            } else if (path.extname(fullPath) === ".json") {
                try {
                    const data = JSON.parse(fs.readFileSync(fullPath, "utf-8"));
                    if (Array.isArray(data)) {
                        components.push(...data);
                    } else {
                        components.push(data);
                    }
                } catch (e: any) {
                    console.error(`Error reading file ${fullPath}:`, e.message);
                }
            }
        }
    }

    walkDir(fdepDir);
    return components;
}

const adapterMap: Record<string, (components: Component[]) => { nodes: any[], edges: any[] }> = {
    "haskell": adaptHaskellComponents,
    "python": adaptPythonComponents,
    // "rescript": adaptRescriptComponents,
    "rust": adaptRustComponents,
    "golang": adaptGoComponents,
    "typescript": adaptTypeScriptComponents,
    // "purescript": adaptPurescriptComponents,
    "javascript": adaptJavascriptComponents
};

const EXT_MAP: Record<string, string[]> = {
    "haskell": [".hs", ".lhs", ".hs-boot"],
    "python": [".py"],
    // "rescript": [".res"],
    "golang": [".go"],
    "rust": [".rs"],
    "typescript": [".ts", ".tsx"],
    // "purescript": [".purs"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"]
};

const INVERSE_EXTS: Record<string, string> = {};
for (const lang in EXT_MAP) {
    for (const ext of EXT_MAP[lang]) {
        INVERSE_EXTS[ext] = lang;
    }
}

function combineSchemas(old: { nodes: any[], edges: any[] }, newSchema: { nodes: any[], edges: any[] }): { nodes: any[], edges: any[] } {
    return {
        nodes: old.nodes.concat(newSchema.nodes),
        edges: old.edges.concat(newSchema.edges)
    };
}

function _processSingleFileWorker(args: [string, string, string, string]) {
    const [codePath, languageStr, rootDirPath, outputBasePath] = args;
    try {
        const extractorInstance = getExtractor(languageStr);
        if (extractorInstance) {
            console.log(`Processing file: ${codePath}`);
            extractorInstance.processFile(codePath);
            const relPath = path.relative(rootDirPath, codePath);
            const jsonRel = path.join(path.dirname(relPath), path.basename(relPath, path.extname(relPath))) + ".json";
            const outPath = path.join(outputBasePath, jsonRel);
            console.log(`Writing output to: ${outPath}`);
            fs.mkdirSync(path.dirname(outPath), { recursive: true });
            extractorInstance.writeToFile(outPath);
            console.log(`Finished writing to: ${outPath}`);
        }
    } catch (e: any) {
        console.error(e.stack);
        console.error(`Unable to process - ${codePath}. Skipping it.`);
    }
}

export function createFdepData(rootDir: string, outputBase = "./output/fdep", graphDir = "./output/graph", clearExisting = true, skipAdaptor = false) {
    process.env.ROOT_DIR = rootDir;
    const rootDirPath = path.resolve(rootDir);
    const languageFileMap: Record<string, string[]> = {};
    const ig = loadGitIgnore(rootDir);

    function walk(dir: string) {
        const files = fs.readdirSync(dir);
        for (const file of files) {
            const fullPath = path.join(dir, file);
            const relativePath = path.relative(rootDirPath, fullPath);
            const ignored = ig.ignores(relativePath);
            if (ignored) {
                continue;
            }
            if (fs.statSync(fullPath).isDirectory()) {
                walk(fullPath);
            } else {
                const language = INVERSE_EXTS[path.extname(fullPath)];
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
    const languageFileCounts = Object.entries(languageFileMap).map(([lang, files]) => `${lang}: ${files.length} files`);
    console.log("Language file map:", languageFileCounts);

    if (fs.existsSync(outputBase) && clearExisting) {
        fs.rmSync(outputBase, { recursive: true, force: true });
    }
    if (fs.existsSync(graphDir) && clearExisting) {
        fs.rmSync(graphDir, { recursive: true, force: true });
    }

    fs.mkdirSync(outputBase, { recursive: true });
    fs.mkdirSync(graphDir, { recursive: true });

    for (const language in languageFileMap) {
        console.log(`Processing ${languageFileMap[language].length} ${language} files...`);
        try {
            const tasksArgs = languageFileMap[language].map(codePath => [codePath, language, rootDirPath, outputBase] as [string, string, string, string]);
            tasksArgs.forEach(_processSingleFileWorker);
        } catch (e: any) {
            console.error(e.stack);
            console.error("ERROR -", e);
        }
    }

    console.log(`Done! All outputs in: ${outputBase}`);
    if (skipAdaptor) {
        return;
    }

    createGraph(outputBase, graphDir);
}

function createGraph(fdepDir: string, graphDir: string) {
    const rawFuncs = loadComponentsWithoutHash(fdepDir);

    const langCompDict: Record<string, Component[]> = {};
    let countUnprocessableFunction = 0;

    for (const func of rawFuncs) {
        try {
            const compLanguage = INVERSE_EXTS[path.extname(func.file_path || "")];
            if (compLanguage) {
                if (!langCompDict[compLanguage]) {
                    langCompDict[compLanguage] = [];
                }
                langCompDict[compLanguage].push(func);
            }
        } catch (e) {
            countUnprocessableFunction++;
        }
    }
    console.log(`Total unprocessable functions: ${countUnprocessableFunction}`);

    const unsupportedLanguages = Object.keys(langCompDict).filter(lang => !adapterMap[lang]);
    if (unsupportedLanguages.length > 0) {
        console.log(`Skipping unsupported languages: ${unsupportedLanguages}`);
    }

    const filteredLangCompDict = Object.fromEntries(
        Object.entries(langCompDict).filter(([lang]) => adapterMap[lang])
    );

    if (Object.keys(filteredLangCompDict).length === 0) {
        console.log("No supported languages found with components.");
        return;
    }

    const schemas = Object.entries(filteredLangCompDict)
        .map(([language, comps]) => adapterMap[language](comps));

    const unifiedSchema = schemas.reduce(combineSchemas, { nodes: [], edges: [] });

    const G = buildGraphFromSchema(unifiedSchema);

    const graphGp = path.join(graphDir, "repo_function_calls.json");

    // Write graph data as JSON since jsnetworkx doesn't support GraphML
    const graphData = {
        nodes: G.nodes(true).map(([node, attrs]) => ({ id: node, ...attrs })),
        edges: G.edges(true).map(([u, v, attrs]) => ({ from: u, to: v, ...attrs })),
    };
    fs.writeFileSync(graphGp, JSON.stringify(graphData, null, 2));

    console.log(`Wrote graph data to ${graphGp}`);
}


function main() {
    const args = process.argv.slice(2);
    if (args.length === 0) {
        console.error("Usage: node main.js <function> <arguments>");
        console.error("Available functions:");
        console.error("  create_fdep_data <root_dir> [output_base] [graph_dir] [clear_existing]");
        return;
    }
    
    const functionName = args[0];
    if (functionName === "create_fdep_data") {
        const rootDir = args[1];
        if (!rootDir) {
            console.error("Please provide a root directory.");
            return;
        }
        
        const outputBase = args[2] || "./output/fdep";
        const graphDir = args[3] || "./output/graph";
        const clearExisting = args[4] !== "false";
        
        console.log(`Creating FDEP data from: ${rootDir}`);
        console.log(`Output base: ${outputBase}`);
        console.log(`Graph directory: ${graphDir}`);
        console.log(`Clear existing: ${clearExisting}`);
        
        createFdepData(rootDir, outputBase, graphDir, clearExisting);
    } else {
        console.error(`Unknown function: ${functionName}`);
    }
}

if (require.main === module) {
    main();
}
