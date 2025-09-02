import * as fs from 'fs';
import * as path from 'path';
import Parser, { SyntaxNode as Node } from 'tree-sitter';
import Go from 'tree-sitter-go';
import { ComponentExtractor } from '../base/component_extractor';

function getNodeText(node: Node, src: string): string {
    return src.substring(node.startIndex, node.endIndex);
}

function findFirstLiteral(node: Node): Node | null {
    const queue: Node[] = [node];
    while (queue.length > 0) {
        const n = queue.shift()!;
        if ([
            "interpreted_string_literal", "raw_string_literal",
            "int_literal", "float_literal", "rune_literal", "imaginary_literal"
        ].includes(n.type)) {
            return n;
        }
        queue.push(...n.children);
    }
    return null;
}

function guessLiteralType(literalNode: Node | null): string | null {
    if (!literalNode) {
        return null;
    }
    const t = literalNode.type;
    if (["interpreted_string_literal", "raw_string_literal"].includes(t)) {
        return "string";
    } else if (t === "int_literal") {
        return "int";
    } else if (t === "float_literal") {
        return "float";
    } else if (t === "rune_literal") {
        return "rune";
    } else if (t === "imaginary_literal") {
        return "complex";
    }
    return null;
}

function getReceiverType(recvNode: Node | null, src: string): string | null {
    if (!recvNode || recvNode.namedChildCount === 0) {
        return null;
    }
    const typeNode = recvNode.namedChildren[0].childForFieldName("type");
    if (typeNode) {
        return getNodeText(typeNode, src).replace(/^\*/, '');
    }
    return null;
}

function extractDocComment(node: Node, src: string): string | null {
    const siblings = node.parent ? node.parent.children : [];
    const idx = siblings.indexOf(node);
    let doc = "";
    for (let i = idx - 1; i >= 0; i--) {
        const sib = siblings[i];
        if (sib.type === "comment") {
            const commentText = getNodeText(sib, src).replace(/\s*[\/|\*]+\s*/g, '').trim();
            doc = commentText + "\\n" + doc;
        } else {
            break;
        }
    }
    return doc.trim() || null;
}

function findRepoRoot(filePath: string): string | null {
    let curr = path.resolve(filePath);
    while (curr !== path.dirname(curr)) {
        if (fs.existsSync(path.join(curr, "go.mod"))) {
            return curr;
        }
        curr = path.dirname(curr);
    }
    return null;
}

function getModulePath(goModPath: string): string | null {
    const content = fs.readFileSync(goModPath, "utf-8");
    for (const line of content.split('\n')) {
        const trimmedLine = line.trim();
        if (trimmedLine.startsWith("module ")) {
            return trimmedLine.split(' ')[1];
        }
    }
    return null;
}

function buildImportPath(filePath: string, repoRoot: string, modulePath: string): string {
    const fileDir = path.dirname(path.resolve(filePath));
    let rel = path.relative(repoRoot, fileDir);
    rel = rel.replace(new RegExp(`\\${path.sep}`, 'g'), "::");
    if (rel === ".") {
        return modulePath;
    }
    if (rel.startsWith(modulePath)) {
        return rel;
    }
    return `${modulePath}::${rel}`;
}

export class GoComponentExtractor implements ComponentExtractor {
    private parser: Parser;
    private importMap: { [key: string]: string[] } = {};
    private packageName: string = "";
    private allComponents: any[] = [];
    private methodReceivers: { [key: string]: string[] } = {};
    private comments: [number, string][] = [];
    private currentFilePath: string = "";
    private repoRoot: string = "";
    private modulePath: string = "";
    private importPath: string = "";

    constructor() {
        this.parser = new Parser();
        this.parser.setLanguage(Go);
    }

    processFile(filePath: string): void {
        this.currentFilePath = filePath;
        const repoRoot = findRepoRoot(filePath);
        if (!repoRoot) {
            throw new Error(`Couldn't find go.mod for file: ${filePath}`);
        }
        this.repoRoot = repoRoot;
        this.modulePath = getModulePath(path.join(repoRoot, "go.mod"))!;
        if (!this.modulePath) {
            throw new Error("Could not parse module path from go.mod");
        }
        this.importPath = buildImportPath(filePath, repoRoot, this.modulePath);

        const src = fs.readFileSync(filePath, 'utf-8');
        const options: Parser.Options = {
            bufferSize: 1024 * 1024,
        };
        const tree = this.parser.parse(src, undefined, options);
        const root = tree.rootNode;

        this.comments = [];
        for (const node of root.children) {
            if (node.type === "comment") {
                this.comments.push([node.startPosition.row + 1, getNodeText(node, src).replace(/\s*\/\s*/, '')]);
            }
        }

        let fileDocstring = "";
        for (const node of root.children) {
            if (node.type === "comment") {
                const commentText = getNodeText(node, src).replace(/\s*\/\s*/, '');
                fileDocstring += commentText + "\\n";
            } else if (node.type === "package_clause") {
                break;
            }
        }

        this.importMap = this._collectImports(root, src);
        this.packageName = this._collectPackageName(src);

        const imports: string[] = [];
        for (const node of root.namedChildren) {
            if (node.type === "import_declaration") {
                for (const imp of node.namedChildren) {
                    if (imp.type === "import_spec_list") {
                        for (const spec of imp.namedChildren) {
                            const pathNode = spec.childForFieldName("path");
                            if (pathNode) {
                                imports.push(getNodeText(pathNode, src).replace(/"/g, ''));
                            }
                        }
                    } else if (imp.type === "import_spec") {
                        const pathNode = imp.childForFieldName("path");
                        if (pathNode) {
                            imports.push(getNodeText(pathNode, src).replace(/"/g, ''));
                        }
                    }
                }
            }
        }

        this.allComponents = [{
            kind: "file",
            file_docstring: fileDocstring.trim(),
            package: this.packageName,
            module_path: this.modulePath,
            import_path: this.importPath,
            imports: imports,
            file_path: path.relative(this.repoRoot, filePath),
        }];

        this.methodReceivers = {};

        for (const node of root.namedChildren) {
            if (["import_declaration", "package_clause"].includes(node.type)) {
                continue;
            } else if (node.type === "function_declaration") {
                const func = this._processFunction(node, src);
                this.allComponents.push(func);
            } else if (node.type === "method_declaration") {
                const method = this._processFunction(node, src);
                this.allComponents.push(method);
                const receiver = method.receiver_type;
                if (receiver) {
                    if (!this.methodReceivers[receiver]) {
                        this.methodReceivers[receiver] = [];
                    }
                    this.methodReceivers[receiver].push(method.name);
                }
            } else if (node.type === "type_declaration") {
                const types = this._processTypeDeclaration(node, src);
                this.allComponents.push(...types);
            } else if (node.type === "var_declaration") {
                this.allComponents.push(...this._processVarDecl(node, src, true));
            } else if (node.type === "const_declaration") {
                this.allComponents.push(...this._processConstDecl(node, src));
            }
        }

        for (const comp of this.allComponents) {
            if (comp.kind === "struct") {
                const structName = comp.name;
                comp.methods = this.methodReceivers[structName] || [];
            }
        }
    }

    writeToFile(outputPath: string): void {
        fs.writeFileSync(outputPath, JSON.stringify(this.allComponents, null, 2), 'utf-8');
    }

    extractAllComponents(): any[] {
        return this.allComponents;
    }

    private _collectPackageName(src: string): string {
        const match = src.match(/^\s*package\s+(\w+)/m);
        return match ? match[1] : "unknown_package";
    }

    private _collectImports(root: Node, src: string): { [key: string]: string[] } {
        const imports: { [key: string]: string[] } = {};
        for (const node of root.namedChildren) {
            if (node.type === "import_declaration") {
                for (const imp of node.namedChildren) {
                    if (imp.type === "import_spec_list") {
                        for (const spec of imp.namedChildren) {
                            const pathNode = spec.childForFieldName("path");
                            if (pathNode) {
                                const module = getNodeText(pathNode, src).replace(/"/g, '');
                                const aliasNode = spec.childForFieldName("name");
                                const alias = aliasNode ? getNodeText(aliasNode, src) : module.split('/').pop()!;
                                if (!imports[alias]) {
                                    imports[alias] = [];
                                }
                                imports[alias].push(module);
                            }
                        }
                    }
                }
            }
        }
        return imports;
    }

    private _functionCompletePath(name: string, receiverType?: string | null): string {
        const filePathRel = path.relative(this.repoRoot, this.currentFilePath);
        if (receiverType) {
            return `${filePathRel}::${receiverType}.${name}`;
        } else {
            return `${filePathRel}::${name}`;
        }
    }

    private _processFunction(node: Node, src: string): any {
        const kind = node.type === "method_declaration" ? "method" : "function";
        let receiverType: string | null = null;
        if (kind === "method") {
            const recvNode = node.childForFieldName("receiver");
            if (recvNode) {
                receiverType = getReceiverType(recvNode, src);
            }
        }

        const nameNode = node.childForFieldName("name");
        const name = nameNode ? getNodeText(nameNode, src) : "";
        const startLine = node.startPosition.row + 1;
        const endLine = node.endPosition.row + 1;
        const code = getNodeText(node, src);
        const doc = extractDocComment(node, src);

        const params: string[] = [];
        const paramTypes: { [key: string]: string } = {};
        const paramList = node.childForFieldName("parameters");
        if (paramList) {
            for (const p of paramList.namedChildren) {
                const names: string[] = [];
                let tname: string | null = null;
                const nameNodes = p.children.filter(c => c.type === "identifier");
                if (nameNodes.length > 0) {
                    names.push(...nameNodes.map(n => getNodeText(n, src)));
                }
                const typeNode = p.childForFieldName("type");
                if (typeNode) {
                    tname = getNodeText(typeNode, src);
                }
                for (const pname of names) {
                    params.push(pname);
                    if (tname) {
                        paramTypes[pname] = tname;
                    }
                }
            }
        }

        let retType: string | null = null;
        const resultNode = node.childForFieldName("result");
        if (resultNode) {
            retType = getNodeText(resultNode, src);
        }

        if (kind === "method") {
            const recvNode = node.childForFieldName("receiver");
            if (recvNode) {
                const receiverChild = recvNode.namedChildren.find(c => c.type === "parameter_declaration");
                if (receiverChild) {
                    const rtypeNode = receiverChild.childForFieldName("type");
                    if (rtypeNode) {
                        receiverType = getNodeText(rtypeNode, src).replace(/^\*/, '');
                    }
                }
            }
        }

        const calls: string[] = [];
        const literals: string[] = [];
        const variables: { name: string, value: string }[] = [];
        const typeDeps = new Set<string>();

        const walk = (n: Node) => {
            if (n.type === "call_expression") {
                const funcNode = n.childForFieldName("function");
                if (funcNode) {
                    calls.push(getNodeText(funcNode, src));
                }
            } else if ([
                "interpreted_string_literal", "raw_string_literal",
                "int_literal", "float_literal", "rune_literal", "imaginary_literal"
            ].includes(n.type)) {
                literals.push(getNodeText(n, src));
            } else if (["assignment_statement", "short_var_declaration"].includes(n.type)) {
                const left = n.childForFieldName("left");
                const right = n.childForFieldName("right");
                if (left && right) {
                    const lefts = left.namedChildren.filter(c => c.type === "identifier");
                    for (const ident of lefts) {
                        const varName = getNodeText(ident, src);
                        const varVal = getNodeText(right, src);
                        variables.push({ name: varName, value: varVal });
                    }
                }
            } else if (["type_conversion_expression", "qualified_type", "pointer_type"].includes(n.type)) {
                typeDeps.add(getNodeText(n, src));
            }
            for (const c of n.children) {
                walk(c);
            }
        };

        const body = node.childForFieldName("body");
        if (body) {
            walk(body);
        }

        const completeFunctionPath = this._functionCompletePath(name, kind === "method" ? receiverType : null);

        return {
            kind: kind,
            name: name,
            module: path.relative(this.repoRoot, this.currentFilePath),
            complete_function_path: completeFunctionPath,
            start_line: startLine,
            end_line: endLine,
            doc_comment: doc,
            parameters: params,
            parameter_types: paramTypes,
            return_type: retType,
            receiver_type: receiverType,
            variables: variables,
            literals: literals,
            function_calls: calls,
            type_dependencies: Array.from(typeDeps),
            code: code,
            import_map: this.importMap,
            package: this.packageName,
            import_path: this.importPath,
            module_path: this.modulePath,
            file_path: path.relative(this.repoRoot, this.currentFilePath),
        };
    }

    private _processTypeDeclaration(node: Node, src: string): any[] {
        const types: any[] = [];
        for (const spec of node.namedChildren) {
            const nameNode = spec.childForFieldName("name");
            const typeNode = spec.childForFieldName("type");
            const typeParamsNode = spec.childForFieldName("type_parameters");

            if (!nameNode || !typeNode) {
                continue;
            }

            const tname = getNodeText(nameNode, src);
            const startLine = spec.startPosition.row + 1;
            const endLine = spec.endPosition.row + 1;
            const code = getNodeText(spec, src);
            const doc = extractDocComment(spec, src);
            const typeKind = typeNode.type;

            if (typeKind === "struct_type") {
                const fields: { name: string | null, type: string, tag: string | null }[] = [];
                const fieldTypes = new Set<string>();
                const fieldList = typeNode.childForFieldName("body");
                if (fieldList) {
                    for (const fld of fieldList.namedChildren) {
                        if (fld.type === "field_declaration") {
                            const fieldNames = fld.children.filter(n => ["identifier", "field_identifier"].includes(n.type)).map(n => getNodeText(n, src));
                            const fieldTypeNode = fld.childForFieldName("type");
                            const fieldType = fieldTypeNode ? getNodeText(fieldTypeNode, src) : null;
                            let tag: string | null = null;
                            const tagNode = fld.namedChildren.find(n => n.type === "tag");
                            if (tagNode) {
                                tag = getNodeText(tagNode, src);
                            }

                            if (fieldNames.length === 0 && fieldType) {
                                fields.push({ name: null, type: fieldType, tag: tag });
                                fieldTypes.add(fieldType);
                            }

                            for (const fname of fieldNames) {
                                if (fieldType) {
                                    fields.push({ name: fname, type: fieldType, tag: tag });
                                    fieldTypes.add(fieldType);
                                }
                            }
                        }
                    }
                }
                types.push({
                    kind: "struct",
                    name: tname,
                    module: path.relative(this.repoRoot, this.currentFilePath),
                    start_line: startLine,
                    end_line: endLine,
                    doc_comment: doc,
                    fields: fields,
                    field_types: Array.from(fieldTypes),
                    methods: [],
                    type_parameters: this._extractTypeParams(typeParamsNode, src),
                    code: code,
                    import_map: this.importMap,
                    package: this.packageName,
                    file_path: path.relative(this.repoRoot, this.currentFilePath),
                });
            } else if (typeKind === "interface_type") {
                const methods: any[] = [];
                const typeDeps = new Set<string>();
                const ifaceBody = typeNode.childForFieldName("body");
                if (ifaceBody) {
                    for (const elem of ifaceBody.namedChildren) {
                        if (elem.type === "method_elem") {
                            const mnameNode = elem.childForFieldName("name");
                            const mname = mnameNode ? getNodeText(mnameNode, src) : null;
                            const { params, paramTypes } = this._extractParamsAndTypes(elem.childForFieldName("parameters"), src);
                            let retType: string | null = null;
                            const resultNode = elem.childForFieldName("result");
                            if (resultNode) {
                                retType = getNodeText(resultNode, src);
                                if (retType) typeDeps.add(retType);
                            }
                            methods.push({
                                name: mname,
                                parameters: params,
                                parameter_types: paramTypes,
                                return_type: retType,
                            });
                        } else if (elem.type === "type_elem") {
                            const typeStr = getNodeText(elem, src);
                            typeDeps.add(typeStr);
                        }
                    }
                }
                types.push({
                    kind: "interface",
                    name: tname,
                    module: path.relative(this.repoRoot, this.currentFilePath),
                    start_line: startLine,
                    end_line: endLine,
                    doc_comment: doc,
                    methods: methods,
                    type_dependencies: Array.from(typeDeps),
                    type_parameters: this._extractTypeParams(typeParamsNode, src),
                    code: code,
                    import_map: this.importMap,
                    package: this.packageName,
                    file_path: path.relative(this.repoRoot, this.currentFilePath),
                });
            } else {
                const aliasedType = getNodeText(typeNode, src);
                types.push({
                    kind: "type_alias",
                    name: tname,
                    module: path.relative(this.repoRoot, this.currentFilePath),
                    aliased_type: aliasedType,
                    start_line: startLine,
                    end_line: endLine,
                    doc_comment: doc,
                    code: code,
                    import_map: this.importMap,
                    package: this.packageName,
                    file_path: path.relative(this.repoRoot, this.currentFilePath),
                });
            }
        }
        return types;
    }

    private _extractTypeParams(node: Node | null, src: string): string[] {
        if (!node) {
            return [];
        }
        const names: string[] = [];
        for (const child of node.namedChildren) {
            if (child.type === "type_parameter_declaration") {
                for (const n of child.namedChildren) {
                    if (n.type === "identifier") {
                        names.push(getNodeText(n, src));
                    }
                }
            }
        }
        return names;
    }

    private _extractParamsAndTypes(paramList: Node | null, src: string): { params: string[], paramTypes: { [key: string]: string } } {
        const params: string[] = [];
        const paramTypes: { [key: string]: string } = {};
        if (paramList) {
            for (const p of paramList.namedChildren) {
                const names: string[] = [];
                let tname: string | null = null;
                const nameNodes = p.children.filter(c => c.type === "identifier");
                if (nameNodes.length > 0) {
                    names.push(...nameNodes.map(n => getNodeText(n, src)));
                }
                const typeNode = p.childForFieldName("type");
                if (typeNode) {
                    tname = getNodeText(typeNode, src);
                }
                for (const pname of names) {
                    params.push(pname);
                    if (tname) {
                        paramTypes[pname] = tname;
                    }
                }
            }
        }
        return { params, paramTypes };
    }

    private _processVarDecl(node: Node, src: string, globalScope: boolean = false): any[] {
        const vars: any[] = [];
        for (const spec of node.namedChildren) {
            const doc = extractDocComment(spec, src);
            for (const child of spec.namedChildren) {
                if (child.type === "identifier") {
                    const name = getNodeText(child, src);
                    let valueNode: Node | null = null;
                    let typeNode: Node | null = null;
                    for (const ch of spec.namedChildren) {
                        if (ch.type === "type") {
                            typeNode = ch;
                        } else if (!["identifier", "type"].includes(ch.type)) {
                            valueNode = ch;
                        }
                    }
                    const value = valueNode ? getNodeText(valueNode, src) : null;
                    let typeStr: string | null = null;
                    const literalNode = valueNode ? findFirstLiteral(valueNode) : null;
                    if (typeNode) {
                        typeStr = getNodeText(typeNode, src);
                    } else if (literalNode) {
                        typeStr = guessLiteralType(literalNode);
                    }

                    vars.push({
                        kind: "variable",
                        name: name,
                        module: path.relative(this.repoRoot, this.currentFilePath),
                        type: typeStr,
                        value: value,
                        doc_comment: doc,
                        location: {
                            start: node.startPosition.row + 1,
                            end: node.endPosition.row + 1,
                        },
                        scope: globalScope ? "global" : "local",
                        file_path: path.relative(this.repoRoot, this.currentFilePath),
                    });
                }
            }
        }
        return vars;
    }

    private _processConstDecl(node: Node, src: string): any[] {
        const consts: any[] = [];
        for (const spec of node.namedChildren) {
            const doc = extractDocComment(spec, src);
            for (const child of spec.namedChildren) {
                if (child.type === "identifier") {
                    const name = getNodeText(child, src);
                    let valueNode: Node | null = null;
                    let typeNode: Node | null = null;
                    for (const ch of spec.namedChildren) {
                        if (ch.type === "type") {
                            typeNode = ch;
                        } else if (!["identifier", "type"].includes(ch.type)) {
                            valueNode = ch;
                        }
                    }
                    const value = valueNode ? getNodeText(valueNode, src) : null;
                    let typeStr: string | null = null;
                    const literalNode = valueNode ? findFirstLiteral(valueNode) : null;
                    if (typeNode) {
                        typeStr = getNodeText(typeNode, src);
                    } else if (literalNode) {
                        typeStr = guessLiteralType(literalNode);
                    }

                    consts.push({
                        kind: "constant",
                        name: name,
                        module: path.relative(this.repoRoot, this.currentFilePath),
                        type: typeStr,
                        value: value,
                        doc_comment: doc,
                        location: {
                            start: node.startPosition.row + 1,
                            end: node.endPosition.row + 1,
                        },
                        file_path: path.relative(this.repoRoot, this.currentFilePath),
                    });
                }
            }
        }
        return consts;
    }
}
