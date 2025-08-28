import Parser, { SyntaxNode } from "tree-sitter";
const TypeScript = require("tree-sitter-typescript");
import * as fs from "fs";
import * as path from "path";
import { ComponentExtractor } from "../base/component_extractor";
import { Component } from "../types/types";
import { chardet, detect } from "chardet";
import { load } from "cheerio";

function parseHtmlToText(filePath: string): string {
    const raw = fs.readFileSync(filePath);
    const guess = detect(raw);
    const encoding = guess || 'utf-8';
    const text = new TextDecoder(encoding).decode(raw);
    const $ = load(text);
    return $.root().text();
}

function findTsconfigDir(rootDir: string, filePath: string, configFilename: string = "tsconfig.json"): string | null {
    let currentDir = path.resolve(path.dirname(filePath));
    const resolvedRootDir = path.resolve(rootDir);

    while (true) {
        const candidate = path.join(currentDir, configFilename);
        if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
            return currentDir;
        }

        const parent = path.dirname(currentDir);
        if (currentDir === resolvedRootDir || parent === currentDir) {
            return null;
        }

        currentDir = parent;
    }
}

function stripJsonComments(text: string): string {
    return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*/g, '');
}

function pathsAliasesFromTsconfig(configFilePath: string): Record<string, string[]> {
    if (!fs.existsSync(configFilePath) || !fs.statSync(configFilePath).isFile()) {
        return {};
    }

    try {
        const raw = fs.readFileSync(configFilePath, 'utf-8');
        const clean = stripJsonComments(raw).trim();
        if (!clean) {
            return {};
        }
        const cfg = JSON.parse(clean);
        const paths = cfg.compilerOptions?.paths || {};
        if (typeof paths === 'object' && paths !== null) {
            return paths;
        }
        return {};
    } catch (e) {
        return {};
    }
}

function resolveCalleeId(calleeId: string, configDir: string, aliasPaths: Record<string, string[]>): string {
    const [importPath, method] = calleeId.includes("::") ? calleeId.split("::", 2) : [calleeId, null];

    const sortedAliases = Object.entries(aliasPaths).sort((a, b) => {
        const aStars = (a[0].match(/\*/g) || []).length;
        const bStars = (b[0].match(/\*/g) || []).length;
        if (aStars !== bStars) {
            return aStars - bStars;
        }
        return b[0].length - a[0].length;
    });

    for (const [aliasPattern, targets] of sortedAliases) {
        if (aliasPattern.includes("*")) {
            const regex = new RegExp("^" + aliasPattern.replace(/\*/g, "(.+)") + "$");
            const m = importPath.match(regex);
            if (!m) {
                continue;
            }
            const wildcards = m.slice(1);
            for (let tpl of targets) {
                let rel = tpl;
                for (const w of wildcards) {
                    rel = rel.replace("*", w);
                }
                const absPath = path.normalize(path.join(configDir, rel));
                return method ? `${absPath}::${method}` : absPath;
            }
        } else {
            if (importPath === aliasPattern) {
                for (let tpl of targets) {
                    const absPath = path.normalize(path.join(configDir, tpl));
                    return method ? `${absPath}::${method}` : absPath;
                }
            }
        }
    }

    return calleeId;
}


export class TypeScriptComponentExtractor implements ComponentExtractor {
    private parser: Parser;
    public allComponents: Component[] = [];
    private readonly tsLanguage: any;
    
    private static readonly UTILITY_TYPES = new Set([
        "Partial", "Required", "Readonly", "Pick", "Omit",
        "ReturnType", "Parameters", "NonNullable", "Record", "InstanceType", "Extract", "Exclude"
    ]);

    constructor() {
        this.parser = new Parser();
        this.tsLanguage = (TypeScript as any).typescript;
        this.parser.setLanguage(this.tsLanguage);
    }

    public processFile(filePath: string): void {
        const code = fs.readFileSync(filePath, 'utf-8');
        const tree = this.parser.parse(code);
        const rootFolder = path.dirname(filePath);
        const imports = this.collectImportsForFile(tree.rootNode, code);
        const components = this.walkNode(tree.rootNode, code, filePath, rootFolder, undefined, imports);

        for (const comp of components) {
            const rootDir = process.env.ROOT_DIR || "";
            if (rootDir && filePath) {
                comp.file_path = path.relative(rootDir, filePath).replace(/\\/g, "/");
            } else {
                comp.file_path = filePath.replace(/\\/g, "/");
            }

            if (!comp.module || comp.file_path.split(".").length === 2) {
                comp.module = comp.file_path;
            }
        }

        this.allComponents = components.filter(c => {
            try {
                JSON.stringify(c);
                return true;
            } catch (e) {
                return false;
            }
        });
    }

    public writeToFile(outputPath: string): void {
        const serializable = this.allComponents.filter(comp => {
            try {
                JSON.stringify(comp);
                return true;
            } catch (e) {
                console.error(`Skipping non-serializable component: ${e}`);
                return false;
            }
        });
        fs.writeFileSync(outputPath, JSON.stringify(serializable, null, 2), "utf-8");
    }

    public extractAllComponents(): Component[] {
        return this.allComponents;
    }

    private getText(node: SyntaxNode, code: string): string {
        return code.substring(node.startIndex, node.endIndex);
    }

    private getRelativePath(filePath: string, rootFolder: string): string {
        const relPath = path.relative(rootFolder, filePath).replace(/\\/g, "/");
        return relPath.endsWith(".ts") ? relPath.slice(0, -3) : relPath;
    }

    private resolveImports(node: SyntaxNode, code: string, currentFilePath: string, rootFolder: string): Record<string, string> {
        const imports: Record<string, string> = {};
        if (node.type === 'import_statement') {
            const importText = this.getText(node, code);
            if (importText.includes('from')) {
                const parts = importText.split('from');
                const sourcePath = parts[1].trim().replace(/['";]/g, "");
                const absSource = path.normalize(path.join(path.dirname(currentFilePath), sourcePath + ".ts"));
                const relativeImportPath = this.getRelativePath(absSource, rootFolder);

                if (importText.includes('{')) {
                    const names = importText.split('{')[1].split('}')[0].split(',');
                    for (let name of names) {
                        name = name.trim();
                        if (name.includes(' as ')) {
                            const [orig, alias] = name.split(' as ').map(s => s.trim());
                            imports[alias] = relativeImportPath;
                        } else {
                            imports[name] = relativeImportPath;
                        }
                    }
                }
            }
        }

        for (const child of node.children) {
            Object.assign(imports, this.resolveImports(child, code, currentFilePath, rootFolder));
        }

        return imports;
    }

    private parseFile(filePath: string): [string, Parser.Tree] {
        const plain = parseHtmlToText(filePath);
        const tree = this.parser.parse(plain);
        return [plain, tree];
    }

    private extractIdent(node: SyntaxNode, code: string): string | null {
        for (const c of node.children) {
            if (['identifier', 'type_identifier', 'property_identifier'].includes(c.type)) {
                return this.getText(c, code);
            }
        }
        return null;
    }

    private parseImports(node: SyntaxNode, code: string): Record<string, string> {
        const imports: Record<string, string> = {};
        if (node.type === 'import_statement') {
            const text = this.getText(node, code);
            if (text.includes('from')) {
                const parts = text.split('from');
                const left = parts[0];
                let right = parts[1].trim().replace(/['";]/g, "");
                if (left.includes('{')) {
                    const names = left.split('{')[1].split('}')[0].split(',');
                    for (let n of names) {
                        n = n.trim();
                        if (n.includes(' as ')) {
                            const [orig, alias] = n.split(' as ').map(x => x.trim());
                            imports[alias] = right;
                        } else {
                            imports[n] = right;
                        }
                    }
                }
            }
        }
        for (const c of node.children) {
            Object.assign(imports, this.parseImports(c, code));
        }
        return imports;
    }

    private collectImportsForFile(rootNode: SyntaxNode, code: string): Record<string, string> {
        const imports: Record<string, string> = {};
        for (const child of rootNode.children) {
            if (child.type === 'import_statement') {
                Object.assign(imports, this.parseImports(child, code));
            }
        }
        return imports;
    }

    private extractTypeAnnotation(node: SyntaxNode, code: string): string | null {
        for (const c of node.children) {
            if (c.type === 'type_annotation' || c.type === 'type') {
                return this.getText(c, code);
            }
        }
        return null;
    }

    private extractEnumMembers(node: SyntaxNode, code: string): { name: string, value: string | null }[] {
        const members: { name: string, value: string | null }[] = [];
        for (const c of node.children) {
            if (c.type === "enum_body") {
                for (const cc of c.children) {
                    if (["enum_assignment", "property_identifier", "identifier"].includes(cc.type)) {
                        let memberName: string | null = null;
                        let memberValue: string | null = null;
                        for (const sub of cc.children) {
                            if (["property_identifier", "identifier"].includes(sub.type)) {
                                memberName = this.getText(sub, code);
                            } else if (!["=", ":"].includes(sub.type)) {
                                memberValue = this.getText(sub, code);
                            }
                        }
                        if (memberName) {
                            members.push({ name: memberName, value: memberValue });
                        }
                    }
                }
            }
        }
        return members;
    }

    private extractModifiers(node: SyntaxNode): Record<string, boolean> {
        const mods: Record<string, boolean> = { "static": false, "abstract": false, "readonly": false, "override": false };
        for (const c of node.children) {
            if (c.type in mods) {
                mods[c.type] = true;
            }
        }
        return mods;
    }

    private extractTypeStructure(node: SyntaxNode, code: string): any {
        if (["type_identifier", "predefined_type"].includes(node.type)) {
            return this.getText(node, code);
        }
        if (node.type === "object_type") {
            const props: Record<string, any> = {};
            for (const child of node.children) {
                if (child.type === "property_signature") {
                    let key: string | null = null;
                    let value: any = null;
                    for (const n of child.children) {
                        if (n.type === "property_identifier") {
                            key = this.getText(n, code);
                        } else if (n.type === "type_annotation" && n.children.length > 1) {
                            value = this.extractTypeStructure(n.children[1], code);
                        }
                    }
                    if (key) {
                        props[key] = value;
                    }
                }
            }
            return { "object_type": props };
        }
        if (node.type === "array_type") {
            for (const c of node.children) {
                if (["type_identifier", "predefined_type", "object_type"].includes(c.type)) {
                    return [this.extractTypeStructure(c, code)];
                }
            }
        }
        return this.getText(node, code);
    }

    private extractTypeParamsStructured(node: SyntaxNode, code: string): any[] {
        for (const c of node.children) {
            if (c.type === 'type_parameters') {
                const params: any[] = [];
                for (const param of c.children) {
                    if (param.type === "type_parameter") {
                        let name: string | null = null;
                        let constraint: any = null;
                        let defaultType: any = null;
                        for (const child of param.children) {
                            if (child.type === "type_identifier") {
                                name = this.getText(child, code);
                            } else if (child.type === "constraint" && child.children.length > 1) {
                                constraint = this.extractTypeStructure(child.children[1], code);
                            } else if (child.type === "default_type" && child.children.length > 1) {
                                defaultType = this.extractTypeStructure(child.children[1], code);
                            }
                        }
                        params.push({
                            name: name,
                            constraint: constraint,
                            default: defaultType,
                        });
                    }
                }
                return params;
            }
        }
        return [];
    }

    private extractTypeParamConstraints(node: SyntaxNode, code: string): string[] {
        const constraints: string[] = [];
        for (const c of node.children) {
            if (c.type === "type_parameters") {
                for (const param of c.children) {
                    if (param.type === "type_parameter") {
                        for (const child of param.children) {
                            if (child.type === "constraint") {
                                constraints.push(this.getText(child, code));
                            }
                        }
                    }
                }
            }
        }
        return constraints;
    }

    private extractGenericTypeDependencies(node: SyntaxNode, code: string): string[] {
        const deps: string[] = [];
        let name: string | null = null;
        const typeArgs: string[] = [];
        for (const c of node.children) {
            if (c.type === "type_identifier") {
                name = this.getText(c, code);
            } else if (c.type === "type_arguments") {
                for (const arg of c.children) {
                    if (arg.type !== ",") {
                        typeArgs.push(this.getText(arg, code));
                    }
                }
            }
        }
        if (name) {
            deps.push(name);
        }
        deps.push(...typeArgs);
        return deps;
    }

    private extractLookupTypeDependencies(node: SyntaxNode, code: string): string[] {
        const deps: string[] = [];
        for (const c of node.children) {
            if (["type_identifier", "literal_type"].includes(c.type)) {
                deps.push(this.getText(c, code));
            } else if (c.type === "lookup_type") {
                deps.push(...this.extractLookupTypeDependencies(c, code));
            }
        }
        return deps;
    }

    private extractConditionalTypeDependencies(node: SyntaxNode, code: string): string[] {
        const deps: string[] = [];
        for (const c of node.children) {
            if (["type_identifier", "predefined_type", "literal_type"].includes(c.type)) {
                deps.push(this.getText(c, code));
            } else if (["consequence", "alternative", "left", "right"].includes(c.type)) {
                for (const cc of c.children) {
                    if (["type_identifier", "predefined_type", "literal_type"].includes(cc.type)) {
                        deps.push(this.getText(cc, code));
                    }
                }
            }
        }
        return deps;
    }

    private extractMappedTypeDependencies(node: SyntaxNode, code: string): string[] {
        const deps: string[] = [];
        for (const c of node.children) {
            if (c.type === "type_identifier") {
                deps.push(this.getText(c, code));
            } else if (c.type === "index_type_query") {
                for (const cc of c.children) {
                    if (cc.type === "type_identifier") {
                        deps.push(this.getText(cc, code));
                    }
                }
            }
        }
        return deps;
    }

    private extractIndexSignatures(node: SyntaxNode, code: string): string[] {
        const indices: string[] = [];
        for (const c of node.children) {
            if (c.type === "index_signature") {
                indices.push(this.getText(c, code));
            }
        }
        return indices;
    }

    private extractDecorators(node: SyntaxNode, code: string): string[] {
        const decorators: string[] = [];
        for (const c of node.children) {
            if (c.type === 'decorator') {
                decorators.push(this.getText(c, code));
            }
        }
        return decorators;
    }

    private extractParameters(node: SyntaxNode, code: string): any[] {
        const params: any[] = [];
        for (const c of node.children) {
            if (c.type === 'formal_parameters') {
                for (const param of c.children) {
                    if (['required_parameter', 'optional_parameter'].includes(param.type)) {
                        let name: string | null = null;
                        let type: string | null = null;
                        let defaultValue: string | null = null;
                        for (const pc of param.children) {
                            if (['identifier', 'pattern', 'type_identifier'].includes(pc.type)) {
                                name = this.getText(pc, code);
                            }
                            if (pc.type === 'type_annotation') {
                                type = this.getText(pc, code);
                            }
                            if (pc.type === '_initializer') {
                                defaultValue = this.getText(pc, code);
                            }
                        }
                        params.push({
                            name: name,
                            type: type,
                            default: defaultValue,
                        });
                    }
                }
            }
        }
        return params;
    }

    private extractTypeParams(node: SyntaxNode, code: string): string | null {
        for (const c of node.children) {
            if (c.type === 'type_parameters' || c.type === 'formal_type_parameters') {
                return this.getText(c, code);
            }
        }
        return null;
    }

    private extractExtendsImplements(node: SyntaxNode, code: string): [string[], string[]] {
        const bases: string[] = [];
        const impls: string[] = [];
        for (const c of node.children) {
            if (c.type === 'class_heritage') {
                for (const cc of c.children) {
                    if (cc.type === 'extends_clause') {
                        for (const base of cc.children) {
                            if ((base as any).fieldName === "value") {
                                const baseName = this.getText(base, code);
                                if (baseName) {
                                    bases.push(baseName);
                                }
                            } else if (['identifier', 'type_identifier'].includes(base.type)) {
                                const baseName = this.getText(base, code);
                                if (baseName) {
                                    bases.push(baseName);
                                }
                            }
                        }
                    }
                    if (cc.type === 'implements_clause') {
                        for (const iface of cc.children) {
                            if (iface.type === 'type') {
                                const ifaceName = this.getText(iface, code);
                                if (ifaceName) {
                                    impls.push(ifaceName);
                                }
                            } else if (['identifier', 'type_identifier'].includes(iface.type)) {
                                const ifaceName = this.getText(iface, code);
                                if (ifaceName) {
                                    impls.push(ifaceName);
                                }
                            }
                        }
                    }
                }
            }
        }
        return [bases, impls];
    }

    private extractInterfaceExtends(node: SyntaxNode, code: string): string[] {
        const parents: string[] = [];
        for (const c of node.children) {
            if (c.type === 'extends_type_clause') {
                for (const cc of c.children) {
                    if (cc.type === 'type') {
                        const parentName = this.getText(cc, code);
                        if (parentName) {
                            parents.push(parentName);
                        }
                    }
                }
            }
        }
        return parents;
    }

    private extractExpressionStatementCalls(node: SyntaxNode, code: string, moduleName: string, filePath: string): any[] {
        const results: any[] = [];
        if (node.type === "expression_statement") {
            const expr = node.children[0];
            if (expr && expr.type === "call_expression") {
                const fn = expr.childForFieldName("function");
                if (fn && fn.type === "member_expression") {
                    const objectNode = fn.childForFieldName("object");
                    const propertyNode = fn.childForFieldName("property");
                    if (objectNode && propertyNode) {
                        const objectName = this.getText(objectNode, code);
                        const propertyName = this.getText(propertyNode, code);
                        const jsdoc = this.extractJsdoc(node, code);
                        const argNodes = expr.childForFieldName("arguments");
                        const args: string[] = [];
                        if (argNodes) {
                            for (const arg of argNodes.children) {
                                if (arg.type !== ',') {
                                    args.push(this.getText(arg, code));
                                }
                            }
                        }
                        results.push({
                            kind: "function_call",
                            module: moduleName,
                            object: objectName,
                            method: propertyName,
                            arguments: args,
                            start_line: node.startPosition.row + 1,
                            end_line: node.endPosition.row + 1,
                            jsdoc: jsdoc,
                        });
                    }
                }
            }
        }
        return results;
    }

    private extractFunctionCalls(filePath: string, node: SyntaxNode, code: string, moduleName: string, imports: Record<string, string>, className?: string, classBases?: string[]): any[] {
        const calls: any[] = [];

        const visit = (n: SyntaxNode) => {
            if (n.type === 'call_expression') {
                const fn = n.childForFieldName('function');
                if (!fn) {
                    return;
                }

                if (fn.type === "member_expression") {
                    const objectNode = fn.childForFieldName("object");
                    const propertyNode = fn.childForFieldName("property");
                    const methodName = propertyNode ? this.getText(propertyNode, code) : null;

                    if (objectNode) {
                        if (objectNode.type === "super") {
                            const baseClass = classBases && classBases.length > 0 ? classBases[0] : "(super_class)";
                            const calleeId = `${moduleName}::${baseClass}.${methodName}`;
                            calls.push({
                                name: `super.${methodName}`,
                                base_name: methodName,
                                resolved_callee: calleeId,
                            });
                        } else if (objectNode.type === "this") {
                            const calleeId = `${moduleName}::${className || "(this_class)"}.${methodName}`;
                            calls.push({
                                name: `this.${methodName}`,
                                base_name: methodName,
                                resolved_callee: calleeId,
                            });
                        } else if (objectNode.type === "identifier") {
                            const objName = this.getText(objectNode, code);
                            const calleeId = `${moduleName}::${objName}.${methodName}`;
                            calls.push({
                                name: `${objName}.${methodName}`,
                                base_name: methodName,
                                resolved_callee: calleeId,
                            });
                        }
                    }
                } else if (fn.type === "identifier") {
                    const calleeText = this.getText(fn, code);
                    const baseName = calleeText;
                    let calleeId: string;
                    if (baseName in imports) {
                        let sourceFile = imports[baseName];
                        if (!sourceFile.endsWith('.ts')) {
                            sourceFile += '.ts';
                        }
                        calleeId = `${sourceFile}::${baseName}`;
                    } else {
                        calleeId = `${filePath}::${baseName}`;
                    }

                    if (calleeId.startsWith("./")) {
                        calls.push({
                            name: calleeText,
                            base_name: baseName,
                            resolved_callee: calleeId,
                        });
                    } else {
                        const rootDir = process.env.ROOT_DIR || "";
                        const configDir = findTsconfigDir(rootDir, filePath);
                        let absoluteCalleeId: string | undefined;
                        if (configDir) {
                            const completeConfigPath = path.join(configDir, "tsconfig.json");
                            const aliasPaths = pathsAliasesFromTsconfig(completeConfigPath);
                            absoluteCalleeId = resolveCalleeId(calleeId, configDir, aliasPaths);
                            if (absoluteCalleeId.startsWith(configDir)) {
                                absoluteCalleeId = path.relative(rootDir, absoluteCalleeId);
                            }
                        } else {
                            console.log(`typescript issue No tsconfig.json found up to ${rootDir}`);
                        }
                        calls.push({
                            name: calleeText,
                            base_name: baseName,
                            resolved_callee: absoluteCalleeId || calleeId,
                        });
                    }
                }

                const args = n.childForFieldName('arguments');
                if (args) {
                    for (const arg of args.children) {
                        visit(arg);
                    }
                }
            }

            for (const c of n.children) {
                visit(c);
            }
        };
        visit(node);
        return calls;
    }

    private extractTypeDependencies(node: SyntaxNode, code: string): string[] {
        const deps = new Set<string>();
        const visit = (n: SyntaxNode) => {
            if (['type_identifier', 'predefined_type', 'nested_type_identifier', 'generic_type'].includes(n.type)) {
                deps.add(this.getText(n, code));
            } else if (['union_type', 'intersection_type', 'parenthesized_type'].includes(n.type)) {
                for (const c of n.children) {
                    if (!["|", "&", "(", ")"].includes(c.type)) {
                        visit(c);
                    }
                }
            } else {
                for (const c of n.children) {
                    visit(c);
                }
            }
        };
        visit(node);
        return Array.from(deps);
    }

    private getFullComponentPath(filePath: string, rootFolder: string, name: string, className?: string): string {
        const relPath = path.relative(rootFolder, filePath).replace(/\\/g, "/");
        if (className) {
            return `${relPath}::${className}.${name}`;
        }
        return `${relPath}::${name}`;
    }

    private getRelativeModulePath(filePath: string, rootFolder: string): string {
        return path.relative(rootFolder, filePath).replace(/\\/g, "/").replace(/^\.\//, "");
    }

    private extractJsdoc(node: SyntaxNode, code: string): string | null {
        let prevSibling = node.previousSibling;
        while (prevSibling) {
            if (prevSibling.type === 'comment') {
                const commentText = this.getText(prevSibling, code);
                if (commentText.trim().startsWith('/**')) {
                    return commentText;
                }
            } else if (prevSibling.type.trim() !== '') {
                break;
            }
            prevSibling = prevSibling.previousSibling;
        }
        return null;
    }

    private walkNode(node: SyntaxNode, code: string, filePath: string, rootFolder: string, context?: any, imports: Record<string, string> = {}): any[] {
        let results: any[] = [];
        const moduleName = this.getRelativeModulePath(filePath, rootFolder);

        if (node.type === 'function_declaration' || node.type === 'function_signature') {
            const fnName = this.extractIdent(node, code);
            const typeSig = this.extractTypeAnnotation(node, code);
            const typeParams = this.extractTypeParams(node, code);
            const typeParamConstraints = this.extractTypeParamConstraints(node, code);
            const decorators = this.extractDecorators(node, code);
            const params = this.extractParameters(node, code);
            const startLine = node.startPosition.row + 1;
            const endLine = node.endPosition.row + 1;
            let body = null;
            for (const c of node.children) {
                if (c.type.includes("block")) {
                    body = c;
                    break;
                }
            }
            const functionCalls = body ? this.extractFunctionCalls(filePath, body, code, moduleName, imports) : [];
            const typeDeps = this.extractTypeDependencies(node, code);
            const jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "function",
                module: moduleName,
                name: fnName,
                type_signature: typeSig,
                type_parameters: typeParams,
                type_param_constraints: typeParamConstraints,
                type_parameters_structured: this.extractTypeParamsStructured(node, code),
                parameters: params,
                decorators: decorators,
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                function_calls: functionCalls,
                type_dependencies: typeDeps,
                parent: context?.parent,
                code: this.getText(node, code),
            });
        }

        if (node.type === 'class_declaration' || node.type === 'class' || node.type === 'abstract_class_declaration') {
            const className = this.extractIdent(node, code);
            const [bases, impls] = this.extractExtendsImplements(node, code);
            const typeParams = this.extractTypeParams(node, code);
            const typeParamConstraints = this.extractTypeParamConstraints(node, code);
            const decorators = this.extractDecorators(node, code);
            const indexSignatures = this.extractIndexSignatures(node, code);
            const startLine = node.startPosition.row + 1;
            const endLine = node.endPosition.row + 1;
            const jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "class",
                module: moduleName,
                name: className,
                type_parameters: typeParams,
                type_param_constraints: typeParamConstraints,
                decorators: decorators,
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                bases: bases,
                implements: impls,
                index_signatures: indexSignatures,
                code: this.getText(node, code),
            });

            for (const c of node.children) {
                if (c.type === 'class_body') {
                    let prevDecorators: string[] = [];
                    for (const m of c.children) {
                        if (m.type === 'decorator') {
                            prevDecorators.push(this.getText(m, code));
                        } else if (m.type === 'method_definition') {
                            let methodName: string | null = null;
                            for (const child of m.children) {
                                if (['property_identifier', 'identifier', 'type_identifier'].includes(child.type)) {
                                    methodName = this.getText(child, code);
                                    break;
                                }
                            }
                            const typeSig = this.extractTypeAnnotation(m, code);
                            let methodBody = null;
                            for (const child of m.children) {
                                if (["statement_block", "body", "block"].includes(child.type)) {
                                    methodBody = child;
                                    break;
                                }
                            }
                            const mCalls = methodBody ? this.extractFunctionCalls(filePath, methodBody, code, moduleName, imports, className || undefined, bases) : [];
                            const mTypeParams = this.extractTypeParams(m, code);
                            const mParams = this.extractParameters(m, code);
                            const mDecorators = prevDecorators;
                            prevDecorators = [];
                            const mStart = m.startPosition.row + 1;
                            const mEnd = m.endPosition.row + 1;
                            const mTypeDeps = this.extractTypeDependencies(m, code);
                            const mMods = this.extractModifiers(m);
                            const isGetter = m.children.some(child => child.type === 'get');
                            const isSetter = m.children.some(child => child.type === 'set');
                            const kind = methodName === "constructor" ? "constructor" : "method";
                            const methodJsdoc = this.extractJsdoc(m, code);
                            results.push({
                                kind: kind,
                                module: moduleName,
                                name: methodName,
                                class: className,
                                type_signature: typeSig,
                                type_parameters: mTypeParams,
                                parameters: mParams,
                                decorators: mDecorators,
                                start_line: mStart,
                                end_line: mEnd,
                                jsdoc: methodJsdoc,
                                function_calls: mCalls,
                                type_dependencies: mTypeDeps,
                                parent: className,
                                static: mMods["static"],
                                abstract: mMods["abstract"],
                                readonly: mMods["readonly"],
                                override: mMods["override"],
                                getter: isGetter,
                                setter: isSetter,
                                code: this.getText(m, code),
                            });
                        } else if (m.type === 'public_field_definition') {
                            let fieldName: string | null = null;
                            for (const child of m.children) {
                                if (['property_identifier', 'identifier', 'type_identifier'].includes(child.type)) {
                                    fieldName = this.getText(child, code);
                                    break;
                                }
                            }
                            const typeSig = this.extractTypeAnnotation(m, code);
                            const mDecorators = prevDecorators;
                            prevDecorators = [];
                            const mStart = m.startPosition.row + 1;
                            const mEnd = m.endPosition.row + 1;
                            const mMods = this.extractModifiers(m);
                            const fieldJsdoc = this.extractJsdoc(m, code);
                            results.push({
                                kind: "field",
                                module: moduleName,
                                name: fieldName,
                                class: className,
                                type_signature: typeSig,
                                decorators: mDecorators,
                                start_line: mStart,
                                end_line: mEnd,
                                jsdoc: fieldJsdoc,
                                parent: className,
                                static: mMods["static"],
                                abstract: mMods["abstract"],
                                readonly: mMods["readonly"],
                                override: mMods["override"],
                                code: this.getText(m, code),
                            });
                        }
                    }
                }
            }
        }

        if (node.type === 'interface_declaration') {
            const interfaceName = this.extractIdent(node, code);
            const typeParams = this.extractTypeParams(node, code);
            const typeParamConstraints = this.extractTypeParamConstraints(node, code);
            const parents = this.extractInterfaceExtends(node, code);
            const indexSignatures = this.extractIndexSignatures(node, code);
            const startLine = node.startPosition.row + 1;
            const endLine = node.endPosition.row + 1;
            let typeDeps: string[] = [];
            for (const c of node.children) {
                if (c.type === "interface_body") {
                    for (const member of c.children) {
                        if (member.type === "property_signature") {
                            for (const propChild of member.children) {
                                if (propChild.type === "type_annotation") {
                                    for (const typeAnnChild of propChild.children) {
                                        if (["type_identifier", "predefined_type", "literal_type"].includes(typeAnnChild.type)) {
                                            typeDeps.push(this.getText(typeAnnChild, code));
                                        } else if (typeAnnChild.type === "generic_type") {
                                            typeDeps.push(...this.extractGenericTypeDependencies(typeAnnChild, code));
                                        } else if (typeAnnChild.type === "lookup_type") {
                                            typeDeps.push(...this.extractLookupTypeDependencies(typeAnnChild, code));
                                        } else if (typeAnnChild.type === "conditional_type") {
                                            typeDeps.push(...this.extractConditionalTypeDependencies(typeAnnChild, code));
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            typeDeps = Array.from(new Set(typeDeps));
            const jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "interface",
                module: moduleName,
                name: interfaceName,
                type_parameters: typeParams,
                type_param_constraints: typeParamConstraints,
                extends: parents,
                index_signatures: indexSignatures,
                type_dependencies: typeDeps,
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                code: this.getText(node, code),
            });
        }

        if (node.type === 'type_alias_declaration') {
            const typeName = this.extractIdent(node, code);
            const typeParams = this.extractTypeParams(node, code);
            const typeParamConstraints = this.extractTypeParamConstraints(node, code);
            let typeDeps = this.extractTypeDependencies(node, code);
            let valueNode = null;
            for (const c of node.children) {
                if (["generic_type", "object_type", "union_type", "lookup_type", "conditional_type"].includes(c.type)) {
                    valueNode = c;
                    break;
                }
                if (c.type === "type" && c.children.length > 0) {
                    if (["generic_type", "object_type", "union_type", "lookup_type", "conditional_type"].includes(c.children[0].type)) {
                        valueNode = c.children[0];
                        break;
                    }
                }
            }

            if (valueNode) {
                if (valueNode.type === "generic_type") {
                    typeDeps.push(...this.extractGenericTypeDependencies(valueNode, code));
                } else if (valueNode.type === "lookup_type") {
                    typeDeps.push(...this.extractLookupTypeDependencies(valueNode, code));
                } else if (valueNode.type === "conditional_type") {
                    typeDeps.push(...this.extractConditionalTypeDependencies(valueNode, code));
                } else if (valueNode.type === "object_type") {
                    for (const child of valueNode.children) {
                        if (child.type === "index_signature") {
                            for (const grandchild of child.children) {
                                if (grandchild.type === "mapped_type_clause") {
                                    typeDeps.push(...this.extractMappedTypeDependencies(grandchild, code));
                                }
                                if (grandchild.type === "type_annotation") {
                                    for (const ggc of grandchild.children) {
                                        if (ggc.type === "lookup_type") {
                                            typeDeps.push(...this.extractLookupTypeDependencies(ggc, code));
                                        }
                                    }
                                }
                                if (grandchild.type === "opting_type_annotation") {
                                    for (const ggc of grandchild.children) {
                                        if (ggc.type === "lookup_type") {
                                            typeDeps.push(...this.extractLookupTypeDependencies(ggc, code));
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else if (valueNode.type === "union_type") {
                    for (const child of valueNode.children) {
                        if (["type_identifier", "literal_type"].includes(child.type)) {
                            typeDeps.push(this.getText(child, code));
                        }
                    }
                }
            }
            const startLine = node.startPosition.row + 1;
            const endLine = node.endPosition.row + 1;
            const jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "type_alias",
                module: moduleName,
                name: typeName,
                type_parameters: typeParams,
                type_param_constraints: typeParamConstraints,
                type_dependencies: Array.from(new Set(typeDeps)),
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                code: this.getText(node, code),
            });
        }

        if (node.type === 'enum_declaration') {
            const enumName = this.extractIdent(node, code);
            const startLine = node.startPosition.row + 1;
            const endLine = node.endPosition.row + 1;
            const jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "enum",
                module: moduleName,
                name: enumName,
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                members: this.extractEnumMembers(node, code),
                code: this.getText(node, code),
            });
        }

        if (node.type === 'import_statement') {
            const jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "import",
                module: moduleName,
                start_line: node.startPosition.row + 1,
                end_line: node.endPosition.row + 1,
                jsdoc: jsdoc,
                code: this.getText(node, code),
            });
        }

        if (node.type === 'export_statement') {
            const jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "export",
                module: moduleName,
                start_line: node.startPosition.row + 1,
                end_line: node.endPosition.row + 1,
                jsdoc: jsdoc,
                code: this.getText(node, code),
            });
        }

        for (const c of node.children) {
            results.push(...this.walkNode(c, code, filePath, rootFolder, context, imports));
        }
        return results;
    }
}
