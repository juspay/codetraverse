import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import * as chardet from 'chardet';
import * as cheerio from 'cheerio';
import Parser, { SyntaxNode } from 'tree-sitter';
const JavaScript = require('tree-sitter-javascript');
import { ComponentExtractor } from '../base/component_extractor';
import { Component } from '../types/types';

// ---------------------------
// Text / file helpers
// ---------------------------
function parseHtmlToText(filePath: string): string {
    const raw = fs.readFileSync(filePath);
    const guess = chardet.detect(raw);
    const encoding = (guess as any)?.encoding || 'utf-8';
    const text = raw.toString(encoding);
    
    // Strip HTML safely if present
    const $ = cheerio.load(text);
    const plain = $.root().text();
    // HTML unescape equivalent to Python's html.unescape
    return plain.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
}

function normSlashes(p: string): string {
    return p.replace(/\\/g, "/");
}

function relpathWithRepo(filePath: string): string {
    /**
     * Return a forward-slashed path prefixed with the repo folder name.
     * Example:
     * ROOT_DIR=/home/me/projects/repo_name
     * file_path=/home/me/projects/repo_name/src/utils/models.js
     * -> "repo_name/src/utils/models.js"
     */
    const fp = normSlashes(filePath);
    const root = process.env.ROOT_DIR || "";
    if (root) {
        const base = path.basename(path.normalize(root)); // "repo_name"
        try {
            const rel = path.relative(root, filePath);
            return normSlashes(path.join(base, rel));
        } catch (error) {
            return fp;
        }
    }
    return fp;
}

// ---------------------------
// Extractor
// ---------------------------
export class JavascriptExtractor implements ComponentExtractor {
    /**
     * Robust JavaScript component extractor backed by Tree-sitter (JS grammar).
     * Produces components with clean paths, function/class/methods, imports/exports,
     * and nested function call discovery with resolution hints.
     */
    
    private static readonly JS_EXTS = [".js", ".mjs", ".cjs", ".jsx"];
    private parser: Parser;
    private allComponents: { [key: string]: any }[] = [];

    constructor() {
        this.parser = new Parser();
        this.parser.setLanguage(JavaScript);
    }

    // ------------- Parsing & text -------------
    private parseFile(filePath: string): { plain: string; tree: Parser.Tree } {
        const plain = parseHtmlToText(filePath);
        
        // Check if file is empty or contains only whitespace
        if (plain.trim().length === 0) {
            console.log(`Skipping empty file: ${filePath}`);
            throw new Error(`Empty file: ${filePath}`);
        }

        // Parse with increased buffer size for large files
        let tree: Parser.Tree;
        try {
            const options: any = {
                bufferSize: 2 * 1024 * 1024, // 2MB buffer size (increased from Haskell's 1MB)
            };
            tree = this.parser.parse(plain, null, options);
        } catch (error) {
            console.log(`Error parsing file ${filePath}: ${(error as Error).message}`);
            throw error;
        }

        if (!tree || !tree.rootNode) {
            console.error(`Invalid parse tree for file ${filePath}`);
            throw new Error(`Invalid parse tree for file ${filePath}`);
        }

        return { plain, tree };
    }

    private getText(node: SyntaxNode | null, plain: string): string {
        if (!node) return "";
        const b = Buffer.from(plain, 'utf-8');
        return b.subarray((node as any).startByte, (node as any).endByte).toString('utf-8');
    }

    // ------------- Public API -------------
    public extractAllComponents(): { [key: string]: any }[] {
        return this.allComponents;
    }

    public processFile(filePath: string): void {
        const { plain, tree } = this.parseFile(filePath);
        
        // repo-prefixed, forward-slashed paths
        const safeFile = relpathWithRepo(path.resolve(filePath));
        const moduleName = safeFile;
        const rootFolder = normSlashes(path.dirname(path.resolve(filePath)));

        const components = this.walkNode(
            tree.rootNode,
            plain,
            safeFile,
            moduleName,
            rootFolder
        );

        const serializable: { [key: string]: any }[] = [];
        for (const comp of components) {
            comp.file_path = comp.file_path || safeFile;
            comp.module = comp.module || moduleName;
            try {
                JSON.stringify(comp);
                serializable.push(comp);
            } catch (error) {
                // Skip non-serializable components
            }
        }
        this.allComponents = serializable;
    }

    public writeToFile(outputPath: string): void {
        fs.mkdirSync(path.dirname(outputPath), { recursive: true });
        
        // Filter and sanitize components to prevent JSON.stringify errors
        const sanitizedComponents = this.allComponents.map(comp => {
            const sanitized = { ...comp };
            
            // Limit code field size to prevent extremely large strings
            if (sanitized.code && typeof sanitized.code === 'string' && sanitized.code.length > 50000) {
                sanitized.code = sanitized.code.substring(0, 50000) + '\n... [truncated due to size]';
            }
            
            // Ensure all fields are serializable
            Object.keys(sanitized).forEach(key => {
                try {
                    JSON.stringify(sanitized[key]);
                } catch (error) {
                    console.warn(`Removing non-serializable field '${key}' from component`);
                    delete sanitized[key];
                }
            });
            
            return sanitized;
        });

        try {
            const jsonString = JSON.stringify(sanitizedComponents, null, 2);
            fs.writeFileSync(outputPath, jsonString, 'utf-8');
        } catch (error) {
            console.error(`Error writing to ${outputPath}:`, (error as Error).message);
            
            // Fallback: write a minimal version with just basic info
            const minimalComponents = sanitizedComponents.map(comp => ({
                kind: comp.kind,
                module: comp.module,
                name: comp.name,
                start_line: comp.start_line,
                end_line: comp.end_line,
                file_path: comp.file_path
            }));
            
            try {
                const minimalJson = JSON.stringify(minimalComponents, null, 2);
                const fallbackPath = outputPath.replace('.json', '_minimal.json');
                fs.writeFileSync(fallbackPath, minimalJson, 'utf-8');
                console.log(`Wrote minimal component data to ${fallbackPath}`);
            } catch (fallbackError) {
                console.error(`Failed to write even minimal data:`, (fallbackError as Error).message);
                throw fallbackError;
            }
        }
    }

    // ------------- Core tree walk -------------
    private walkNode(
        node: SyntaxNode,
        plain: string,
        filePath: string,
        moduleName: string,
        rootFolder: string
    ): { [key: string]: any }[] {
        const comps: { [key: string]: any }[] = [];

        // Functions
        if (node.type === "function_declaration" || node.type === "generator_function_declaration") {
            comps.push(this.extractFunctionLike(node, plain, moduleName, filePath, node.type.includes("generator")));
        }

        // Arrow function attached to variable declarator
        if (node.type === "arrow_function") {
            const parent = node.parent;
            if (parent && parent.type === "variable_declarator") {
                const nameNode = parent.childForFieldName("name");
                const name = nameNode ? this.getText(nameNode, plain) : "<anon>";
                const paramsNode = node.childForFieldName("parameter") || node.childForFieldName("parameters");
                const params = paramsNode ? this.getText(paramsNode, plain) : "()";
                const calls = this.extractCalls(node, plain, moduleName, null, null);
                
                comps.push({
                    kind: "arrow_function",
                    module: moduleName,
                    name: name,
                    parameters: params,
                    function_calls: calls,
                    start_line: this.getStartLine(parent),
                    end_line: this.getEndLine(parent),
                    code: this.getText(parent, plain),
                    file_path: filePath
                });
            }
        }

        // Class + methods
        if (node.type === "class_declaration") {
            comps.push(...this.extractClass(node, plain, moduleName, filePath));
        }

        // Variable declarations (var / let / const)
        if (node.type === "variable_declaration" || node.type === "lexical_declaration") {
            comps.push(...this.extractVariables(node, plain, moduleName, filePath));
        }

        // Imports/exports
        if (node.type === "import_statement") {
            comps.push(this.extractImport(node, plain, moduleName, filePath));
        }
        if (node.type === "export_statement") {
            comps.push(...this.extractExport(node, plain, moduleName, filePath));
        }

        // Statements & expressions — useful for structure/graph
        const statementKinds: { [key: string]: string } = {
            "if_statement": "if_statement",
            "for_statement": "for_statement",
            "while_statement": "while_statement",
            "do_statement": "do_statement",
            "switch_statement": "switch_statement",
            "try_statement": "try_statement",
            "throw_statement": "throw_statement",
            "debugger_statement": "debugger_statement",
            "with_statement": "with_statement",
            "break_statement": "break_statement",
            "continue_statement": "continue_statement",
            "return_statement": "return_statement",
            "empty_statement": "empty_statement",
            "labeled_statement": "labeled_statement"
        };

        if (node.type in statementKinds) {
            const comp: { [key: string]: any } = {
                kind: statementKinds[node.type],
                module: moduleName,
                start_line: this.getStartLine(node),
                end_line: this.getEndLine(node),
                code: this.getText(node, plain),
                file_path: filePath
            };

            // enrich with key fields if present
            if (node.type === "if_statement") {
                const cond = node.childForFieldName("condition");
                comp.condition = cond ? this.getText(cond, plain) : null;
            }
            if (node.type === "for_statement") {
                comp.initializer = this.safeText(node.childForFieldName("initializer"), plain);
                comp.condition = this.safeText(node.childForFieldName("condition"), plain);
                comp.increment = this.safeText(node.childForFieldName("increment"), plain);
            }
            if (node.type === "while_statement" || node.type === "do_statement") {
                const cond = node.childForFieldName("condition");
                comp.condition = cond ? this.getText(cond, plain) : null;
            }
            if (node.type === "switch_statement") {
                const valueNode = node.childForFieldName("value");
                comp.value = valueNode ? this.getText(valueNode, plain) : null;
            }
            if (node.type === "with_statement") {
                const obj = node.childForFieldName("object");
                comp.object = obj ? this.getText(obj, plain) : null;
            }
            if (node.type === "break_statement" || node.type === "continue_statement") {
                const label = node.childForFieldName("label");
                comp.label = label ? this.getText(label, plain) : null;
            }
            if (node.type === "return_statement") {
                let valueNode: SyntaxNode | null = null;
                for (const ch of node.children) {
                    if (ch.type !== "return" && ch.type !== ";") {
                        valueNode = ch;
                        break;
                    }
                }
                comp.value = valueNode ? this.getText(valueNode, plain) : null;
            }
            comps.push(comp);
        }

        // Top-level literal expression statements
        if (node.type === "number" || node.type === "string" || node.type === "template_string") {
            const parent = node.parent;
            const grandparent = parent?.parent;
            if (parent && parent.type === "expression_statement" && 
                grandparent && grandparent.type === "program") {
                comps.push({
                    kind: node.type,
                    module: moduleName,
                    name: this.getText(node, plain),
                    start_line: this.getStartLine(node),
                    end_line: this.getEndLine(node),
                    code: this.getText(node, plain),
                    file_path: filePath
                });
            }
        }

        // Assignments / augmented
        if (node.type === "assignment_expression") {
            comps.push(this.extractAssignment(node, plain, moduleName, filePath));
        }
        if (node.type === "augmented_assignment_expression") {
            comps.push(this.extractAugAssignment(node, plain, moduleName, filePath));
        }

        // Member/subscript/parenthesized (structural nodes)
        if (node.type === "member_expression") {
            comps.push(this.extractMember(node, plain, moduleName, filePath));
        }
        if (node.type === "subscript_expression") {
            comps.push(this.extractSubscript(node, plain, moduleName, filePath));
        }
        if (node.type === "parenthesized_expression") {
            const inner = node.children.length > 1 ? node.children[1] : null;
            comps.push({
                kind: "parenthesized_expression",
                module: moduleName,
                expression: inner ? this.getText(inner, plain) : null,
                start_line: this.getStartLine(node),
                end_line: this.getEndLine(node),
                code: this.getText(node, plain),
                file_path: filePath
            });
        }

        // New / await / yield / ternary / sequence
        if (node.type === "new_expression") {
            const ctor = node.childForFieldName("constructor");
            const args = node.childForFieldName("arguments");
            comps.push({
                kind: "new_expression",
                module: moduleName,
                constructor: this.safeText(ctor, plain),
                arguments: this.safeText(args, plain),
                start_line: this.getStartLine(node),
                end_line: this.getEndLine(node),
                code: this.getText(node, plain),
                file_path: filePath
            });
        }
        if (node.type === "await_expression") {
            comps.push(this.simple(node, plain, moduleName, filePath, "await_expression"));
        }
        if (node.type === "yield_expression") {
            comps.push(this.simple(node, plain, moduleName, filePath, "yield_expression"));
        }
        if (node.type === "ternary_expression") {
            comps.push(this.extractTernary(node, plain, moduleName, filePath));
        }
        if (node.type === "sequence_expression") {
            const exprs = node.children.filter(ch => ch.type !== ",").map(ch => this.getText(ch, plain));
            comps.push({
                kind: "sequence_expression",
                module: moduleName,
                expressions: exprs,
                start_line: this.getStartLine(node),
                end_line: this.getEndLine(node),
                code: this.getText(node, plain),
                file_path: filePath
            });
        }

        // Recurse
        for (const child of node.children) {
            comps.push(...this.walkNode(child, plain, filePath, moduleName, rootFolder));
        }

        return comps;
    }

    // ------------- Extract helpers -------------
    private safeText(node: SyntaxNode | null, plain: string): string | null {
        if (!node) return null;
        return this.getText(node, plain);
    }

    private getStartLine(node: SyntaxNode): number {
        return (node as any).startPoint?.[0] ? (node as any).startPoint[0] + 1 : 1;
    }

    private getEndLine(node: SyntaxNode): number {
        return (node as any).endPoint?.[0] ? (node as any).endPoint[0] + 1 : 1;
    }

    private simple(node: SyntaxNode, plain: string, moduleName: string, filePath: string, kind: string): { [key: string]: any } {
        return {
            kind: kind,
            module: moduleName,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: this.getText(node, plain),
            file_path: filePath
        };
    }

    private extractFunctionLike(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string,
        isGenerator: boolean = false
    ): { [key: string]: any } {
        const nameNode = node.childForFieldName("name");
        const name = this.safeText(nameNode, plain) || "<anon>";
        const paramsNode = node.childForFieldName("parameters");
        const params = this.safeText(paramsNode, plain) || "()";
        const bodyNode = node.childForFieldName("body");
        const calls = bodyNode ? this.extractCalls(bodyNode, plain, moduleName, null, null) : [];

        return {
            kind: isGenerator ? "generator_function" : "function",
            module: moduleName,
            name: name,
            parameters: params,
            function_calls: calls,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: this.getText(node, plain),
            file_path: filePath
        };
    }

    private extractClass(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any }[] {
        const out: { [key: string]: any }[] = [];
        const nameNode = node.childForFieldName("name");
        const name = this.safeText(nameNode, plain) || "<anon>";
        const bases: string[] = [];

        const superNode = node.childForFieldName("superclass");
        if (superNode) {
            const raw = this.getText(superNode, plain).trim();
            const match = raw.match(/^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*/);
            if (match) {
                bases.push(match[0]);
            }
        } else {
            // Fallback: parse header before the first '{'
            const header = this.getText(node, plain).split("{")[0];
            const match = header.match(/\bextends\s+([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)?)/);
            if (match) {
                bases.push(match[1]);
            }
        }

        out.push({
            kind: "class",
            module: moduleName,
            name: name,
            bases: bases,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: this.getText(node, plain),
            file_path: filePath
        });

        const body = node.childForFieldName("body");
        if (body) {
            for (const m of body.children) {
                if (m.type === "method_definition") {
                    const methodNameNode = m.childForFieldName("name");
                    const methodName = this.safeText(methodNameNode, plain) || "<anon>";
                    const paramsNode = m.childForFieldName("parameters");
                    const params = this.safeText(paramsNode, plain) || "()";
                    const bodyNode = m.childForFieldName("body");
                    const calls = bodyNode ? this.extractCalls(bodyNode, plain, moduleName, name, bases) : [];

                    out.push({
                        kind: methodName === "constructor" ? "constructor" : "method",
                        module: moduleName,
                        class: name,
                        name: methodName,
                        parameters: params,
                        function_calls: calls,
                        start_line: this.getStartLine(m),
                        end_line: this.getEndLine(m),
                        code: this.getText(m, plain),
                        file_path: filePath
                    });
                }
            }
        }

        return out;
    }

    private extractVariables(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any }[] {
        /**
         * Emit variables AND (FIX) emit a component for function/class expressions bound to a variable name.
         */
        const comps: { [key: string]: any }[] = [];
        const kind = node.type === "variable_declaration" ? "var" : "let_or_const";

        for (const d of node.namedChildren) {
            if (d.type === "variable_declarator") {
                const nameNode = d.childForFieldName("name");
                const name = this.safeText(nameNode, plain);
                const valueNode = d.childForFieldName("value");

                // Function/class expressions become proper components
                if (valueNode && ["function_expression", "generator_function", "class"].includes(valueNode.type)) {
                    if (valueNode.type === "class") {
                        // class expression under variable
                        const bases: string[] = [];
                        const superNode = valueNode.childForFieldName("superclass");
                        if (superNode) {
                            const raw = this.getText(superNode, plain).trim();
                            const match = raw.match(/^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*/);
                            if (match) {
                                bases.push(match[0]);
                            }
                        } else {
                            const header = this.getText(valueNode, plain).split("{")[0];
                            const match = header.match(/\bextends\s+([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)?)/);
                            if (match) {
                                bases.push(match[1]);
                            }
                        }

                        comps.push({
                            kind: "class",
                            module: moduleName,
                            name: name,
                            bases: bases,
                            start_line: this.getStartLine(valueNode),
                            end_line: this.getEndLine(valueNode),
                            code: this.getText(valueNode, plain),
                            file_path: filePath
                        });
                    } else {
                        // function / generator function expression
                        const paramsNode = valueNode.childForFieldName("parameters");
                        const params = this.safeText(paramsNode, plain) || "()";
                        const bodyNode = valueNode.childForFieldName("body");
                        const calls = bodyNode ? this.extractCalls(bodyNode, plain, moduleName, null, null) : [];

                        comps.push({
                            kind: valueNode.type === "generator_function" ? "generator_function" : "function",
                            module: moduleName,
                            name: name,
                            parameters: params,
                            function_calls: calls,
                            start_line: this.getStartLine(valueNode),
                            end_line: this.getEndLine(valueNode),
                            code: this.getText(valueNode, plain),
                            file_path: filePath
                        });
                    }

                    // optionally also emit the variable entry (kept for completeness)
                    comps.push({
                        kind: "variable",
                        storage: kind,
                        module: moduleName,
                        name: name,
                        start_line: this.getStartLine(node),
                        end_line: this.getEndLine(node),
                        code: this.getText(node, plain),
                        file_path: filePath
                    });
                    continue;
                }

                // Plain variables
                comps.push({
                    kind: "variable",
                    storage: kind,
                    module: moduleName,
                    name: name,
                    start_line: this.getStartLine(node),
                    end_line: this.getEndLine(node),
                    code: this.getText(node, plain),
                    file_path: filePath
                });
            }
        }

        return comps;
    }

    private extractImport(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any } {
        const text = this.getText(node, plain).trim();
        const srcNode = node.childForFieldName("source");
        const srcRaw = this.safeText(srcNode, plain);
        let source: string | null = null;
        
        if (srcRaw) {
            source = srcRaw.trim();
            if ((source.startsWith("'") && source.endsWith("'")) || 
                (source.startsWith('"') && source.endsWith('"'))) {
                source = source.slice(1, -1);
            }
        }

        const details: { [key: string]: any } = {
            default: null,
            named: [], // list of {"exported": "...", "local": "..."}
            namespace: null, // alias for *
            side_effect: false
        };

        // Named/default/namespace import parsing
        const mNamed = text.match(/import\s*{([^}]+)}\s*from\s*['"][^'"]+['"]/);
        const mDefault = text.match(/import\s+([A-Za-z0-9_$]+)\s*(?:,|from)\s*['"][^'"]+['"]/);
        const mNamespace = text.match(/import\s+\*\s+as\s+([A-Za-z0-9_$]+)\s*from\s*['"][^'"]+['"]/);
        const mSide = text.match(/^\s*import\s+['"][^'"]+['"]\s*;?\s*$/);

        if (mNamed) {
            const raw = mNamed[1];
            const names = raw.split(",").map(x => x.trim()).filter(x => x);
            for (const n of names) {
                if (n.includes(" as ")) {
                    const [exported, local] = n.split(" as ").map(p => p.trim());
                    details.named.push({ exported, local });
                } else {
                    details.named.push({ exported: n, local: n });
                }
            }
        }
        if (mNamespace) {
            details.namespace = mNamespace[1];
        }
        if (mDefault && !mNamespace) {
            details.default = mDefault[1];
        }
        if (mSide && !details.default && !details.named.length && !details.namespace) {
            details.side_effect = true;
        }

        return {
            kind: "import",
            module: moduleName,
            source: source,
            details: details,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: text,
            file_path: filePath
        };
    }

    private extractExport(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any }[] {
        /**
         * Emit real components for 'export' wrappers (functions/classes/variables),
         * and also return a small 'export' meta item describing the export.
         * This fixes the 'export default function foo(){}' showing up as just 'export'.
         */
        const text = this.getText(node, plain).trim();
        const out: { [key: string]: any }[] = [];

        // 1) If this export directly wraps a declaration, emit the declaration(s)
        // as normal components so they appear as 'function'/'class'/etc.
        for (const ch of node.children) {
            if (ch.type === "function_declaration" || ch.type === "generator_function_declaration") {
                out.push(this.extractFunctionLike(ch, plain, moduleName, filePath, ch.type.includes("generator")));
            } else if (ch.type === "class_declaration") {
                out.push(...this.extractClass(ch, plain, moduleName, filePath));
            } else if (ch.type === "variable_declaration" || ch.type === "lexical_declaration") {
                out.push(...this.extractVariables(ch, plain, moduleName, filePath));
            }
        }

        // 2) Build a compact export meta record (covers re-exports & default/named)
        // (kept for downstream tooling that reads export info)
        const mStar = text.match(/export\s+\*\s+from\s+['"]([^'"]+)['"]/);
        if (mStar) {
            out.push({
                kind: "export",
                module: moduleName,
                name: "*",
                reexport: true,
                source: mStar[1],
                start_line: this.getStartLine(node),
                end_line: this.getEndLine(node),
                code: text,
                file_path: filePath
            });
            return out;
        }

        const mNamed = text.match(/export\s*{([^}]+)}\s*(?:from\s+['"]([^'"]+)['"])?/);
        if (mNamed) {
            const raw = mNamed[1];
            const src = mNamed[2];
            const names = raw.split(",").map(x => x.trim()).filter(x => x);
            for (const n of names) {
                let exported: string, alias: string;
                if (n.includes(" as ")) {
                    [exported, alias] = n.split(" as ").map(p => p.trim());
                } else {
                    exported = alias = n;
                }
                out.push({
                    kind: "export",
                    module: moduleName,
                    name: alias, // local export name
                    exported: exported, // original symbol name
                    reexport: !!src,
                    source: src,
                    start_line: this.getStartLine(node),
                    end_line: this.getEndLine(node),
                    code: text,
                    file_path: filePath
                });
            }
            return out;
        }

        // default export (try to capture the identifier if present)
        if (/export\s+default\s+/.test(text)) {
            const mId = text.match(/export\s+default\s+([A-Za-z0-9_$]+)/);
            const name = mId ? mId[1] : "default";
            out.push({
                kind: "export",
                module: moduleName,
                name: name, // will be the identifier if there is one (e.g., 'type_func'), else 'default'
                default: true,
                start_line: this.getStartLine(node),
                end_line: this.getEndLine(node),
                code: text,
                file_path: filePath
            });
            return out;
        }

        // generic/fallback export meta
        out.push({
            kind: "export",
            module: moduleName,
            name: null,
            default: false,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: text,
            file_path: filePath
        });
        return out;
    }

    private extractAssignment(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any } {
        const left = this.safeText(node.childForFieldName("left"), plain);
        const right = this.safeText(node.childForFieldName("right"), plain);
        return {
            kind: "assignment_expression",
            module: moduleName,
            left: left,
            right: right,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: this.getText(node, plain),
            file_path: filePath
        };
    }

    private extractAugAssignment(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any } {
        const left = this.safeText(node.childForFieldName("left"), plain);
        const op = this.safeText(node.childForFieldName("operator"), plain);
        const right = this.safeText(node.childForFieldName("right"), plain);
        return {
            kind: "augmented_assignment_expression",
            module: moduleName,
            left: left,
            operator: op,
            right: right,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: this.getText(node, plain),
            file_path: filePath
        };
    }

    private extractMember(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any } {
        const obj = this.safeText(node.childForFieldName("object"), plain);
        const prop = this.safeText(node.childForFieldName("property"), plain);
        return {
            kind: "member_expression",
            module: moduleName,
            object: obj,
            property: prop,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: this.getText(node, plain),
            file_path: filePath
        };
    }

    private extractSubscript(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any } {
        const obj = this.safeText(node.childForFieldName("object"), plain);
        const idx = this.safeText(node.childForFieldName("index"), plain);
        return {
            kind: "subscript_expression",
            module: moduleName,
            object: obj,
            index: idx,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: this.getText(node, plain),
            file_path: filePath
        };
    }

    private extractTernary(
        node: SyntaxNode,
        plain: string,
        moduleName: string,
        filePath: string
    ): { [key: string]: any } {
        const condition = this.safeText(node.childForFieldName("condition"), plain);
        const consequence = this.safeText(node.childForFieldName("consequence"), plain);
        const alternative = this.safeText(node.childForFieldName("alternative"), plain);
        return {
            kind: "ternary_expression",
            module: moduleName,
            condition: condition,
            consequence: consequence,
            alternative: alternative,
            start_line: this.getStartLine(node),
            end_line: this.getEndLine(node),
            code: this.getText(node, plain),
            file_path: filePath
        };
    }

    // ------------- Call extraction -------------
    private extractCalls(
        node: SyntaxNode | null,
        plain: string,
        moduleName: string,
        classCtx: string | null,
        bases: string[] | null
    ): { [key: string]: any }[] {
        /**
         * Recursively collect call expressions as dictionaries:
         * - handles identifier calls, member calls, and (fix) super()
         * - attaches best-effort local resolution hint
         */
        const calls: { [key: string]: any }[] = [];
        if (!node) return calls;

        const visit = (n: SyntaxNode): void => {
            if (n.type === "call_expression") {
                const fn = n.childForFieldName("function");
                const argsNode = n.childForFieldName("arguments");
                const args: string[] = [];
                
                if (argsNode) {
                    for (const a of argsNode.children) {
                        if (a.type !== ",") {
                            args.push(this.getText(a, plain));
                        }
                    }
                }

                let rec: string | null = null;
                let prop: string | null = null;
                let funcName: string | null = null;
                let resolvedHint: string | null = null;

                if (fn) {
                    if (fn.type === "member_expression") {
                        const objNode = fn.childForFieldName("object");
                        const propNode = fn.childForFieldName("property");
                        rec = this.safeText(objNode, plain);
                        prop = this.safeText(propNode, plain);
                        funcName = (rec && prop) ? `${rec}.${prop}` : this.getText(fn, plain);

                        if (rec === "this" && classCtx && prop) {
                            resolvedHint = `${moduleName}::${classCtx}::${prop}`;
                        } else if (rec === "super" && bases && bases.length > 0) {
                            const base0 = bases[0];
                            resolvedHint = `${moduleName}::${base0}.${prop}`;
                        } else if (rec && /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(rec)) {
                            resolvedHint = `${moduleName}::${rec}.${prop}`;
                        }
                    } else if (fn.type === "identifier") {
                        funcName = this.getText(fn, plain);
                        // FIX: super()
                        if (funcName === "super" && bases && bases.length > 0) {
                            resolvedHint = `${moduleName}::${bases[0]}.constructor`;
                        } else {
                            resolvedHint = `${moduleName}::${funcName}`;
                        }
                    } else {
                        funcName = this.getText(fn, plain);
                    }
                }

                calls.push({
                    function: funcName,
                    arguments: "(" + args.join(", ") + ")",
                    code: this.getText(n, plain),
                    receiver: rec,
                    property: prop,
                    resolved_hint: resolvedHint
                });

                // Recurse into args too (calls inside args)
                if (argsNode) {
                    for (const ch of argsNode.children) {
                        visit(ch);
                    }
                }
            }

            for (const ch of n.children) {
                visit(ch);
            }
        };

        visit(node);
        return calls;
    }
}
