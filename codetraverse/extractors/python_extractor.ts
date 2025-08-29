import * as fs from "fs";
import * as path from "path";
import * as chardet from "chardet";
import * as cheerio from "cheerio";
import Parser, { SyntaxNode } from "tree-sitter";
const Python = require("tree-sitter-python"); // Assuming tree-sitter-python is installed
import { ComponentExtractor } from "../base/component_extractor";
import { Component, FunctionCall, Parameter, Field, Variant, Import, TypeUsed, Literal, Variable, Span } from "../types/types";

// Helper function to parse HTML to plain text
function parseHtmlToText(filePath: string): string {
    const raw = fs.readFileSync(filePath);
    const guess = chardet.detect(raw);
    const encoding = (guess as any).encoding || 'utf-8';
    const text = raw.toString(encoding);
    const $ = cheerio.load(text);
    const plain = $.root().text(); // Use .root() to get the root element and then its text
    return plain;
}

export class PythonComponentExtractor implements ComponentExtractor {
    private parser: Parser;
    private allComponents: Component[] = [];
    private imports: { [key: string]: string } = {}; // To store import mappings
    private projectRoot: string | undefined;

    constructor() {
        this.parser = new Parser();
        this.parser.setLanguage(Python);
    }

    private getText(node: SyntaxNode, plain: string): string {
        return plain.substring(node.startIndex, node.endIndex);
    }

    private extractDecorators(node: SyntaxNode, plain: string): string[] | null {
        const decs: string[] = [];
        for (const child of node.children) {
            if (child.type === "decorator") {
                decs.push(this.getText(child, plain).trim());
            }
        }
        return decs.length > 0 ? decs : null;
    }

    private extractParameters(node: SyntaxNode, plain: string): Parameter[] | null {
        const params: Parameter[] = [];
        for (const p of node.namedChildren) {
            if (p.type === "identifier") {
                params.push({ name: this.getText(p, plain), type: null, filePath: "" });
            } else if (p.type === "typed_parameter") {
                const nameNode = p.childForFieldName("name");
                const typeNode = p.childForFieldName("type");
                const name = nameNode ? this.getText(nameNode, plain) : null;
                const annotation = typeNode ? this.getText(typeNode, plain) : null;
                if (name) {
                    params.push({ name: name, type: annotation, filePath: "" });
                }
            }
        }
        return params.length > 0 ? params : null;
    }

    private extractTypeAlias(node: SyntaxNode, plain: string, moduleName: string): Component {
        const nameNode = node.childForFieldName("name");
        const valueNode = node.childForFieldName("value");
        return {
            kind: "type_alias",
            module: moduleName,
            name: nameNode ? this.getText(nameNode, plain) : null,
            typeSignature: valueNode ? this.getText(valueNode, plain) : null,
            startLine: node.startPosition.row + 1,
            endLine: node.endPosition.row + 1,
            code: this.getText(node, plain),
            filePath: "", // Will be filled later
        };
    }

    private extractFunctionCalls(node: SyntaxNode, plain: string, moduleName: string, relPath: string): FunctionCall[] {
        let calls: FunctionCall[] = [];

        if (node.type === "call") {
            const fn = node.childForFieldName("function") || node.children[0];
            if (fn) {
                const full = this.getText(fn, plain).trim();
                const name = full.split("(")[0];

                let resolved: string | null = null;

                // 1) If it was imported via “from X import Y”
                if (this.imports[name]) {
                    const mod = this.imports[name]; // e.g. "codetraverse.utils.networkx_graph"
                    const modPath = mod.replace(/\./g, "/") + ".py"; // → "codetraverse/utils/networkx_graph.py"
                    resolved = `${modPath}::${name}`;
                }
                // 2) dotted attribute off an import: X.Y.Z
                else if (name.includes(".")) {
                    const parts = name.split(".");
                    const root = parts[0];
                    const leaf = parts[parts.length - 1];
                    if (this.imports[root]) {
                        const mod = this.imports[root];
                        const modPath = mod.replace(/\./g, "/") + ".py";
                        resolved = `${modPath}::${leaf}`;
                    }
                }

                // 3) fallback to local definition
                if (!resolved) {
                    resolved = `${relPath}::${name}`;
                }

                calls.push({
                    name: name,
                    type: "function_call", // Added missing 'type' property
                    base: name.split(".").pop() || name,
                    context: "function_call", // This needs to be more specific based on context
                    modules: [resolved],
                });
            }
        }

        // recurse
        for (const child of node.children) {
            calls = calls.concat(this.extractFunctionCalls(child, plain, moduleName, relPath));
        }
        return calls;
    }

    private walkNode(node: SyntaxNode, plain: string, filePath: string, rootFolder: string, relPath: string): Component[] {
        let comps: Component[] = [];
        const moduleName = path.relative(rootFolder, filePath).replace(/\\/g, "/");

        // helper to know if a node is nested inside any class_definition
        const isInsideClass = (n: SyntaxNode): boolean => {
            let p = n.parent;
            while (p) {
                if (p.type === "class_definition") {
                    return true;
                }
                p = p.parent;
            }
            return false;
        };

        // ————————— imports —————————
        if (node.type === "import_statement") {
            const code = this.getText(node, plain).trim();
            const parts = code.split(/\s+/, 2);
            if (parts.length === 2) {
                const raw = parts[1];
                for (const name of raw.split(",")) {
                    const trimmedName = name.trim();
                    if (!trimmedName) continue;
                    comps.push({
                        kind: "import",
                        module: moduleName,
                        name: trimmedName,
                        code: code,
                        startLine: node.startPosition.row + 1,
                        endLine: node.endPosition.row + 1,
                        filePath: "", // Will be filled later
                    });
                }
            }
        }

        if (node.type === "import_from_statement") {
            const code = this.getText(node, plain).trim();
            const tokens = code.split(/\s+/);
            if (tokens.length >= 4 && tokens[0] === "from" && tokens[2] === "import") {
                const source = tokens[1];
                const raw = code.substring(code.indexOf("import") + "import".length).trim();
                for (const name of raw.split(",")) {
                    const trimmedName = name.trim();
                    if (!trimmedName) continue;
                    comps.push({
                        kind: "import",
                        module: moduleName,
                        name: trimmedName,
                        from: source,
                        code: code,
                        startLine: node.startPosition.row + 1,
                        endLine: node.endPosition.row + 1,
                        filePath: "", // Will be filled later
                    });
                }
            }
        }

        // — assignments (module vars) —
        if (node.type === "assignment") {
            const lhs = node.childForFieldName("left");
            if (lhs && lhs.type === "identifier") {
                comps.push({
                    kind: "variable",
                    module: moduleName,
                    name: this.getText(lhs, plain),
                    code: this.getText(node, plain),
                    startLine: node.startPosition.row + 1,
                    endLine: node.endPosition.row + 1,
                    filePath: "", // Will be filled later
                });
            }
        }

        // — type aliases —
        if (node.type === "type_alias_statement") {
            comps.push(this.extractTypeAlias(node, plain, moduleName));
        }

        // — only module-level function / async definitions (skip those inside a class) —
        if (["function_definition", "async_function_definition"].includes(node.type) && !isInsideClass(node)) {
            const nameNode = node.childForFieldName("name");
            const name = nameNode ? this.getText(nameNode, plain) : "<anon>";

            // parameters
            let params: Parameter[] | null = null;
            const pn = node.childForFieldName("parameters");
            if (pn) {
                params = this.extractParameters(pn, plain);
            }

            // return annotation
            let returns: string | null = null;
            const rt = node.childForFieldName("return_type");
            if (rt) {
                returns = this.getText(rt, plain);
            }

            // decorators and calls
            const decs = this.extractDecorators(node, plain);
            const calls = this.extractFunctionCalls(node, plain, moduleName, relPath);

            comps.push({
                kind: node.type.startsWith("async_") ? "async_function" : "function",
                module: moduleName,
                name: name,
                decorators: decs,
                parameters: params,
                returns: returns,
                startLine: node.startPosition.row + 1,
                endLine: node.endPosition.row + 1,
                code: this.getText(node, plain),
                functionCalls: calls,
                filePath: "", // Will be filled later
            });
        }

        // — class definitions + methods —
        if (node.type === "class_definition") {
            const nameNode = node.childForFieldName("name");
            const clsName = nameNode ? this.getText(nameNode, plain) : "<anon>";
            const decs = this.extractDecorators(node, plain);

            // base-classes in parentheses
            const bases: string[] = [];
            const bp = node.childForFieldName("arguments");
            if (bp) {
                for (const b of bp.namedChildren) {
                    bases.push(this.getText(b, plain));
                }
            }

            comps.push({
                kind: "class",
                module: moduleName,
                name: clsName,
                decorators: decs,
                bases: bases.length > 0 ? bases : null,
                startLine: node.startPosition.row + 1,
                endLine: node.endPosition.row + 1,
                code: this.getText(node, plain),
                filePath: "", // Will be filled later
            });

            // now pick up its methods
            const body = node.childForFieldName("body");
            if (body) {
                for (const m of body.namedChildren) {
                    if (["function_definition", "async_function_definition"].includes(m.type)) {
                        const mn = m.childForFieldName("name");
                        const mname = mn ? this.getText(mn, plain) : "<anon>";

                        const mpn = m.childForFieldName("parameters");
                        const mparams = mpn ? this.extractParameters(mpn, plain) : null;

                        const mdecs = this.extractDecorators(m, plain);
                        const mcalls = this.extractFunctionCalls(m, plain, moduleName, relPath);

                        comps.push({
                            kind: m.type.startsWith("async_") ? "async_method" : "method",
                            module: moduleName,
                            class: clsName,
                            name: mname,
                            decorators: mdecs,
                            parameters: mparams,
                            startLine: m.startPosition.row + 1,
                            endLine: m.endPosition.row + 1,
                            code: this.getText(m, plain),
                            functionCalls: mcalls,
                            filePath: "", // Will be filled later
                        });
                    }
                }
            }
        }

        // recurse into children
        for (const child of node.children) {
            comps = comps.concat(this.walkNode(child, plain, filePath, rootFolder, relPath));
        }

        return comps;
    }

    public parseFile(filePath: string): { plain: string; tree: Parser.Tree } {
        const plain = parseHtmlToText(filePath);
        const options: Parser.Options = {
            bufferSize: 1024 * 1024,
        };
        const tree = this.parser.parse(plain, null, options);
        return { plain, tree };
    }

    public extractFromFile(filepath: string, rootFolder: string, relPath: string): Component[] {
        const { plain, tree } = this.parseFile(filepath);
        return this.walkNode(tree.rootNode, plain, filepath, rootFolder, relPath);
    }

    public extractFromFolder(folder: string): Component[] {
        let out: Component[] = [];
        this.projectRoot = process.env.ROOT_DIR || "";
        const absFolder = path.resolve(folder);

        const files = fs.readdirSync(absFolder, { recursive: true, withFileTypes: true });

        for (const dirent of files) {
            if (dirent.isFile() && dirent.name.endsWith('.py')) {
                const file_path = path.join(dirent.path, dirent.name);
                const rel = path.relative(this.projectRoot, file_path).replace(/\\/g, "/");
                out = out.concat(this.extractFromFile(file_path, absFolder, rel));
            }
        }
        return out;
    }

    public processFile(filePath: string): void {
        const { plain, tree } = this.parseFile(filePath);
        const rootFolder = path.dirname(filePath);

        // build import map
        this.imports = {};
        const root = tree.rootNode;
        for (const child of root.children) {
            if (child.type === "import_statement") {
                const code = this.getText(child, plain).trim();
                const parts = code.split(/\s+/);
                if (parts[0] === "import") {
                    for (const token of parts.slice(1).join(" ").split(",")) {
                        const trimmedToken = token.trim();
                        if (trimmedToken.includes(" as ")) {
                            const [mod, alias] = trimmedToken.split(" as ").map(s => s.trim());
                            this.imports[alias] = mod;
                        } else {
                            this.imports[trimmedToken.split(/\s+/)[0]] = trimmedToken.split(/\s+/)[0];
                        }
                    }
                }
            } else if (child.type === "import_from_statement") {
                const code = this.getText(child, plain).trim();
                const toks = code.split(/\s+/);
                if (toks[0] === "from" && toks.includes("import")) {
                    const srcModule = toks[1];
                    const names = code.substring(code.indexOf("import") + "import".length).split(",");
                    for (const n of names) {
                        const trimmedN = n.trim();
                        if (trimmedN.includes(" as ")) {
                            const [orig, alias] = trimmedN.split(" as ").map(s => s.trim());
                            this.imports[alias] = srcModule; // map the alias to the module
                        } else {
                            this.imports[trimmedN] = srcModule;
                        }
                    }
                }
            }
        }

        this.projectRoot = process.env.ROOT_DIR || "";
        const rel = path.relative(this.projectRoot, filePath).replace(/\\/g, "/");

        // now extract everything
        const raw = this.extractFromFile(filePath, rootFolder, rel);

        // stamp each comp with a file_path
        for (const c of raw) {
            c.filePath = rel;
            c.module = c.module || rel;
        }

        // JSON-filter
        this.allComponents = raw.filter(c => this.isJsonable(c));
    }

    private isJsonable(x: any): boolean {
        try {
            JSON.stringify(x);
            return true;
        } catch (e) {
            return false;
        }
    }

    public writeToFile(outputPath: string): void {
        fs.mkdirSync(path.dirname(outputPath), { recursive: true });
        fs.writeFileSync(outputPath, JSON.stringify(this.allComponents, null, 2), "utf8");
    }

    public extractAllComponents(): Component[] {
        return this.allComponents;
    }
}