import Parser, { SyntaxNode } from "tree-sitter";
import { FunctionCall } from "../types/types";
import Rust from "tree-sitter-rust";
import fs from "fs";
import path from "path";
import { ComponentExtractor } from "../base/component_extractor";
import { Component, Span, Parameter, Field, Variant, Call, Literal, Variable, TypeUsed, Import } from "../types/types";

interface RustImport {
    path: string;
    name: string;
}

export class RustComponentExtractor implements ComponentExtractor {
    private parser: Parser;
    private readonly rsLanguage: any;
    private rawComponents: Component[] = [];
    private importMappings: Record<string, string> = {};
    private wildcardImports: string[] = [];
    private currentFilePath: string = "";
    private currentModulePath: string = "";
    private moduleStack: string[] = [];

    constructor() {
        this.parser = new Parser();
        this.rsLanguage = Rust;
        this.parser.setLanguage(this.rsLanguage);
    }

    processFile(filePath: string): void {
        const src = fs.readFileSync(filePath);
        const tree = this.parser.parse(src.toString());
        this.rawComponents = [];
        this.importMappings = {};
        this.wildcardImports = [];
        this.currentFilePath = filePath;
        this.currentModulePath = this.getModulePathFromFile(filePath);
        this.moduleStack = [this.currentModulePath];
        this.collectImports(tree.rootNode, src);
        for (const node of tree.rootNode.namedChildren) {
            const comp = this.processNode(node, src, filePath);
            if (comp) {
                this.rawComponents.push(comp);
            }
        }
    }

    private getModulePathFromFile(filePath: string): string {
        filePath = filePath.replace(/\\/g, '/');
        const pathWithoutExt = path.parse(filePath).dir + '/' + path.parse(filePath).name;
        const parts = pathWithoutExt.split('/');
        let srcIndex = -1;
        for (let i = 0; i < parts.length; i++) {
            if (parts[i] === 'src') {
                srcIndex = i;
                break;
            }
        }
        if (srcIndex === -1) {
            return `crate::${path.basename(pathWithoutExt)}`;
        }
        let moduleParts = parts.slice(srcIndex + 1);
        if (moduleParts.length === 0) {
            return "crate";
        }
        if (moduleParts.length === 1) {
            if (['main', 'lib'].includes(moduleParts[0])) {
                return "crate";
            } else {
                return `crate::${moduleParts[0]}`;
            }
        }
        if (moduleParts[moduleParts.length - 1] === 'mod') {
            moduleParts = moduleParts.slice(0, -1);
        }
        if (moduleParts.length === 0) {
            return "crate";
        }
        return "crate::" + moduleParts.join("::");
    }

    private collectImports(rootNode: SyntaxNode, src: Buffer): void {
        const walkForImports = (node: SyntaxNode) => {
            if (node.type === 'use_declaration') {
                this.processUseDeclarationForMapping(node, src);
            }
            for (const child of node.namedChildren) {
                walkForImports(child);
            }
        };
        walkForImports(rootNode);
    }

    private processUseDeclarationForMapping(node: SyntaxNode, src: Buffer): void {
        const argNode = node.childForFieldName('argument');
        if (argNode) {
            this.extractImportMappings(argNode, src, "");
        }
    }

    private extractImportMappings(node: SyntaxNode, src: Buffer, basePath: string): void {
        if (node.type === 'identifier') {
            const symbol = src.slice(node.startIndex, node.endIndex).toString('utf8');
            const fullPath = basePath ? `${basePath}::${symbol}` : symbol;
            this.importMappings[symbol] = fullPath;
        } else if (node.type === 'scoped_identifier') {
            const pathNode = node.childForFieldName('path');
            const nameNode = node.childForFieldName('name');
            if (pathNode && nameNode) {
                const pathStr = src.slice(pathNode.startIndex, pathNode.endIndex).toString('utf8');
                const nameStr = src.slice(nameNode.startIndex, nameNode.endIndex).toString('utf8');
                const fullPath = basePath ? `${basePath}::${pathStr}::${nameStr}` : `${pathStr}::${nameStr}`;
                this.importMappings[nameStr] = fullPath;
            }
        } else if (node.type === 'scoped_use_list') {
            const pathNode = node.childForFieldName('path');
            const listNode = node.childForFieldName('list');
            if (pathNode && listNode) {
                const pathStr = src.slice(pathNode.startIndex, pathNode.endIndex).toString('utf8');
                const currentBase = basePath ? `${basePath}::${pathStr}` : pathStr;
                for (const child of listNode.namedChildren) {
                    this.extractImportMappings(child, src, currentBase);
                }
            }
        } else if (node.type === 'use_list') {
            for (const child of node.namedChildren) {
                this.extractImportMappings(child, src, basePath);
            }
        } else if (node.type === 'use_wildcard') {
            if (basePath) {
                this.wildcardImports.push(basePath);
            }
        } else if (node.type === 'crate') {
            return;
        }
    }

    private resolveSymbolPath(symbolPath: string): string {
        const parts = symbolPath.split("::");
        if (parts.length === 0) {
            return symbolPath;
        }
        const firstSymbol = parts[0].trim();
        if (this.importMappings[firstSymbol]) {
            const fullFirstPart = this.importMappings[firstSymbol];
            if (parts.length === 1) {
                return fullFirstPart;
            } else {
                const remainingParts = parts.slice(1).join("::");
                return `${fullFirstPart}::${remainingParts}`;
            }
        }

        for (const wildcard of this.wildcardImports) {
            // This is a simplification. In a real scenario, we would need to check
            // if the symbol actually exists in the wildcard-imported module.
            // For now, we'll assume it might and construct a potential path.
            const potentialPath = `${wildcard}::${symbolPath}`;
            // Here you might want to have a list of all known symbols to check against.
            // For now, we just return the first potential path.
            return potentialPath;
        }

        return symbolPath;
    }

    writeToFile(outputPath: string): void {
        fs.writeFileSync(outputPath, JSON.stringify(this.rawComponents, null, 2), "utf-8");
    }

    extractAllComponents(): Component[] {
        return this.rawComponents;
    }

    private extractTypeInfo(node: SyntaxNode | null, src: Buffer): string | null {
        if (!node) {
            return null;
        }
        const typeText = src.slice(node.startIndex, node.endIndex).toString('utf8');
        if (node.type === 'generic_type') {
            const baseType = node.childForFieldName('type');
            const typeArgs = node.childForFieldName('type_arguments');
            const baseText = baseType ? src.slice(baseType.startIndex, baseType.endIndex).toString('utf8') : '';
            const argsText = typeArgs ? src.slice(typeArgs.startIndex, typeArgs.endIndex).toString('utf8') : '';
            return `${baseText}${argsText}`;
        }
        return typeText;
    }

    private extractVisibility(node: SyntaxNode, src: Buffer): string {
        for (const child of node.children) {
            if (child.type === 'visibility_modifier') {
                return src.slice(child.startIndex, child.endIndex).toString('utf8');
            }
        }
        return 'private';
    }

    private extractAttributes(node: SyntaxNode, src: Buffer): string[] {
        const attributes: string[] = [];
        const parent = node.parent;
        if (parent) {
            for (const sibling of parent.children) {
                if (sibling.type === 'attribute_item' && sibling.endPosition.row < node.startPosition.row) {
                    const attrText = src.slice(sibling.startIndex, sibling.endIndex).toString('utf8');
                    attributes.push(attrText);
                }
            }
        }
        return attributes;
    }

    private processNode(node: SyntaxNode, src: Buffer, filePath: string, currentModulePath: string | null = null): Component | null {
        if (currentModulePath === null) {
            currentModulePath = this.moduleStack.length > 0 ? this.moduleStack[this.moduleStack.length - 1] : this.currentModulePath;
        }
        const primaryKinds = new Set([
            'mod_item', 'use_declaration', 'struct_item', 'enum_item', 'union_item',
            'type_alias_item', 'trait_item', 'impl_item', 'const_item', 'static_item',
            'function_item', 'closure_expression', 'let_declaration', 'type_item'
        ]);
        if (!primaryKinds.has(node.type)) {
            return null;
        }
        const name = this.extractName(node, src);
        let fullModulePath: string;
        if (node.type === 'mod_item') {
            fullModulePath = currentModulePath !== "crate" ? `${currentModulePath}::${name}` : `crate::${name}`;
        } else {
            fullModulePath = currentModulePath;
        }
        const span: Span = {
            startLine: node.startPosition.row + 1,
            endLine: node.endPosition.row + 1,
            startByte: node.startIndex,
            endByte: node.endIndex,
        };
        const comp: Component = {
            kind: node.type,
            name: name,
            startLine: span.startLine,
            endLine: span.endLine,
            filePath: filePath,
            module: fullModulePath,
            span: span,
            code: src.slice(node.startIndex, node.endIndex).toString('utf8'),
            visibility: this.extractVisibility(node, src),
            attributes: this.extractAttributes(node, src),
            children: [],
            parameters: [],
            returnType: null,
            typeParameters: [],
            whereClause: null,
            functionCalls: [],
            methodCalls: [],
            macroCalls: [],
            literals: [],
            variables: [],
            typesUsed: [],
            imports: [],
            fields: [],
            variants: [],
            traitBounds: [],
            lifetimes: []
        };
        this.extractNodeSpecificInfo(node, src, comp);
        if (node.type === 'mod_item') {
            this.moduleStack.push(fullModulePath);
            this.traverseAndExtract(node, src, comp, filePath);
            this.moduleStack.pop();
        } else {
            this.traverseAndExtract(node, src, comp, filePath);
        }
        return comp;
    }

    private extractName(node: SyntaxNode, src: Buffer): string {
        if (node.type === 'impl_item') {
            return this.extractImplName(node, src);
        } else if (node.type === 'use_declaration') {
            return this.extractUseName(node, src);
        } else {
            const nameNode = node.childForFieldName('name') ||
                node.childForFieldName('path') ||
                node.childForFieldName('pattern');
            if (nameNode) {
                return src.slice(nameNode.startIndex, nameNode.endIndex).toString('utf8');
            }
            return node.type;
        }
    }

    private extractImplName(node: SyntaxNode, src: Buffer): string {
        const traitNode = node.childForFieldName('trait');
        const typeNode = node.childForFieldName('type');
        if (traitNode && typeNode) {
            const traitName = src.slice(traitNode.startIndex, traitNode.endIndex).toString('utf8');
            const typeName = src.slice(typeNode.startIndex, typeNode.endIndex).toString('utf8');
            return `${traitName} for ${typeName}`;
        } else if (typeNode) {
            const typeName = src.slice(typeNode.startIndex, typeNode.endIndex).toString('utf8');
            return `impl ${typeName}`;
        }
        return 'impl_item';
    }

    private extractUseName(node: SyntaxNode, src: Buffer): string {
        const argNode = node.childForFieldName('argument');
        if (argNode) {
            return this.extractUseModulePath(argNode, src);
        }
        return 'use_declaration';
    }

    private extractUseModulePath(node: SyntaxNode, src: Buffer): string {
        if (node.type === 'scoped_use_list') {
            const pathNode = node.childForFieldName('path');
            if (pathNode) {
                return src.slice(pathNode.startIndex, pathNode.endIndex).toString('utf8');
            }
        } else if (node.type === 'scoped_identifier' || node.type === 'identifier') {
            return src.slice(node.startIndex, node.endIndex).toString('utf8');
        } else if (node.type === 'crate') {
            return 'crate';
        }
        return src.slice(node.startIndex, node.endIndex).toString('utf8') || '';
    }

    private extractNodeSpecificInfo(node: SyntaxNode, src: Buffer, comp: Component): void {
        switch (node.type) {
            case 'function_item':
                this.extractFunctionInfo(node, src, comp);
                break;
            case 'struct_item':
                this.extractStructInfo(node, src, comp);
                break;
            case 'enum_item':
                this.extractEnumInfo(node, src, comp);
                break;
            case 'trait_item':
                this.extractTraitInfo(node, src, comp);
                break;
            case 'impl_item':
                this.extractImplInfo(node, src, comp);
                break;
            case 'use_declaration':
                this.extractUseInfo(node, src, comp);
                break;
            case 'mod_item':
                this.extractModInfo(node, src, comp);
                break;
        }
    }

    private extractFunctionInfo(node: SyntaxNode, src: Buffer, comp: Component): void {
        const paramsNode = node.childForFieldName('parameters');
        if (paramsNode) {
            for (const param of paramsNode.namedChildren) {
                if (param.type === 'parameter') {
                    const pattern = param.childForFieldName('pattern');
                    const typeNode = param.childForFieldName('type');
                    const paramInfo: Parameter = {
                        name: pattern ? src.slice(pattern.startIndex, pattern.endIndex).toString('utf8') : '',
                        type: this.extractTypeInfo(typeNode, src),
                        filePath: comp.filePath || ''
                    };
                    comp.parameters.push(paramInfo);
                } else if (param.type === 'self_parameter') {
                    comp.parameters.push({ name: 'self', type: 'Self', filePath: comp.filePath || '' });
                }
            }
        }
        const retNode = node.childForFieldName('return_type');
        if (retNode) {
            comp.returnType = this.extractTypeInfo(retNode, src);
        }
        const typeParams = node.childForFieldName('type_parameters');
        if (typeParams) {
            comp.typeParameters.push(src.slice(typeParams.startIndex, typeParams.endIndex).toString('utf8'));
        }
        const whereNode = node.children.find(child => child.type === 'where_clause');
        if (whereNode) {
            comp.whereClause = src.slice(whereNode.startIndex, whereNode.endIndex).toString('utf8');
        }
    }

    private extractStructInfo(node: SyntaxNode, src: Buffer, comp: Component): void {
        const body = node.childForFieldName('body');
        if (body) {
            if (body.type === 'field_declaration_list') {
                for (const field of body.namedChildren) {
                    if (field.type === 'field_declaration') {
                        const nameNode = field.childForFieldName('name');
                        const typeNode = field.childForFieldName('type');
                        const fieldInfo: Field = {
                            name: nameNode ? src.slice(nameNode.startIndex, nameNode.endIndex).toString('utf8') : '',
                            type: this.extractTypeInfo(typeNode, src) || '',
                            visibility: this.extractVisibility(field, src),
                            filePath: comp.filePath || ''
                        };
                        comp.fields.push(fieldInfo);
                    }
                }
            } else if (body.type === 'ordered_field_declaration_list') {
                for (let i = 0; i < body.namedChildren.length; i++) {
                    const field = body.namedChildren[i];
                    const fieldInfo: Field = {
                        name: `field_${i}`,
                        type: this.extractTypeInfo(field, src) || '',
                        visibility: this.extractVisibility(field, src),
                        filePath: comp.filePath || ''
                    };
                    comp.fields.push(fieldInfo);
                }
            }
        }
    }

    private extractEnumInfo(node: SyntaxNode, src: Buffer, comp: Component): void {
        const body = node.childForFieldName('body');
        if (body && body.type === 'enum_variant_list') {
            for (const variant of body.namedChildren) {
                if (variant.type === 'enum_variant') {
                    const nameNode = variant.childForFieldName('name');
                    const variantInfo: Variant = {
                        name: nameNode ? src.slice(nameNode.startIndex, nameNode.endIndex).toString('utf8') : '',
                        fields: []
                    };
                    const valueNode = variant.childForFieldName('value');
                    if (valueNode) {
                        if (valueNode.type === 'field_declaration_list') {
                            for (const field of valueNode.namedChildren) {
                                const fieldName = field.childForFieldName('name');
                                const fieldType = field.childForFieldName('type');
                                variantInfo.fields.push({
                                    name: fieldName ? src.slice(fieldName.startIndex, fieldName.endIndex).toString('utf8') : '',
                                    type: this.extractTypeInfo(fieldType, src) || '',
                                    filePath: comp.filePath || ''
                                });
                            }
                        } else if (valueNode.type === 'ordered_field_declaration_list') {
                            for (let i = 0; i < valueNode.namedChildren.length; i++) {
                                const field = valueNode.namedChildren[i];
                                variantInfo.fields.push({
                                    name: `field_${i}`,
                                    type: this.extractTypeInfo(field, src) || '',
                                    filePath: comp.filePath || ''
                                });
                            }
                        }
                    }
                    comp.variants.push(variantInfo);
                }
            }
        }
    }

    private extractTraitInfo(node: SyntaxNode, src: Buffer, comp: Component): void {
        // TODO: Implement trait info extraction
    }

    private extractImplInfo(node: SyntaxNode, src: Buffer, comp: Component): void {
        const typeParams = node.childForFieldName('type_parameters');
        if (typeParams) {
            comp.typeParameters.push(src.slice(typeParams.startIndex, typeParams.endIndex).toString('utf8'));
        }
    }

    private extractUseInfo(node: SyntaxNode, src: Buffer, comp: Component): void {
        const extractImportsFromNode = (n: SyntaxNode, basePath: string = "") => {
            if (n.type === 'identifier') {
                const importPath = basePath ? `${basePath}::${src.slice(n.startIndex, n.endIndex).toString('utf8')}` : src.slice(n.startIndex, n.endIndex).toString('utf8');
                comp.imports.push({ path: importPath, name: importPath.split('::').pop() || '' });
            } else if (n.type === 'scoped_identifier') {
                const pathNode = n.childForFieldName('path');
                const nameNode = n.childForFieldName('name');
                if (pathNode && nameNode) {
                    const pathStr = src.slice(pathNode.startIndex, pathNode.endIndex).toString('utf8');
                    const nameStr = src.slice(nameNode.startIndex, nameNode.endIndex).toString('utf8');
                    const fullPath = basePath ? `${basePath}::${pathStr}::${nameStr}` : `${pathStr}::${nameStr}`;
                    comp.imports.push({ path: fullPath, name: nameStr });
                }
            } else if (n.type === 'scoped_use_list') {
                const pathNode = n.childForFieldName('path');
                const listNode = n.childForFieldName('list');
                if (pathNode && listNode) {
                    const pathStr = src.slice(pathNode.startIndex, pathNode.endIndex).toString('utf8');
                    const currentBase = basePath ? `${basePath}::${pathStr}` : pathStr;
                    for (const child of listNode.namedChildren) {
                        extractImportsFromNode(child, currentBase);
                    }
                }
            } else if (n.type === 'use_list') {
                for (const child of n.namedChildren) {
                    extractImportsFromNode(child, basePath);
                }
            }
        };
        const argNode = node.childForFieldName('argument');
        if (argNode) {
            extractImportsFromNode(argNode);
        }
    }

    private extractModInfo(node: SyntaxNode, src: Buffer, comp: Component): void {
        // TODO: Implement mod info extraction
    }

    private traverseAndExtract(node: SyntaxNode, src: Buffer, comp: Component, filePath: string): void {
        const walk = (n: SyntaxNode) => {
            const t = n.type;
            const primaryKinds = new Set([
                'mod_item', 'use_declaration', 'struct_item', 'enum_item', 'union_item',
                'type_alias_item', 'trait_item', 'impl_item', 'const_item', 'static_item',
                'function_item', 'closure_expression', 'type_item'
            ]);
            if (primaryKinds.has(t) && n !== node) {
                const child = this.processNode(n, src, filePath, this.moduleStack.length > 0 ? this.moduleStack[this.moduleStack.length - 1] : this.currentModulePath);
                if (child) {
                    comp.children.push(child);
                }
                return;
            }
            if (t === 'call_expression') {
                const fn = n.childForFieldName('function');
                if (fn) {
                    if (fn.type === 'field_expression') {
                        const valueNode = fn.childForFieldName('value');
                        const fieldNode = fn.childForFieldName('field');
                        if (valueNode && fieldNode) {
                            const receiverText = src.slice(valueNode.startIndex, valueNode.endIndex).toString('utf8');
                            const methodText = src.slice(fieldNode.startIndex, fieldNode.endIndex).toString('utf8');
                            const resolvedReceiver = this.resolveSymbolPath(receiverText);
                            const methodInfo: FunctionCall = {
                                name: `${receiverText}.${methodText}`,
                                type: "method_call",
                                context: "function_call",
                                modules: [resolvedReceiver],
                                base: methodText,
                                receiver: receiverText,
                            };
                            comp.functionCalls?.push(methodInfo);
                        }
                    } else {
                        const fnText = src.slice(fn.startIndex, fn.endIndex).toString('utf8');
                        const resolvedFn = this.resolveSymbolPath(fnText);
                        const callInfo: FunctionCall = {
                            name: fnText,
                            type: "function_call",
                            context: "function_call",
                            modules: [resolvedFn],
                            base: fnText,
                        };
                        comp.functionCalls?.push(callInfo);
                    }
                }
            } else if (t === 'macro_invocation') {
                const macroNode = n.childForFieldName('macro');
                if (macroNode) {
                    const macroText = src.slice(macroNode.startIndex, macroNode.endIndex).toString('utf8');
                    const resolvedMacro = this.resolveSymbolPath(macroText);
                    const macroInfo: FunctionCall = {
                        name: macroText,
                        type: "macro_call",
                        context: "macro_invocation",
                        modules: [resolvedMacro],
                        base: macroText,
                    };
                    comp.functionCalls?.push(macroInfo);
                }
            } else if (['string_literal', 'integer_literal', 'float_literal',
                'boolean_literal', 'char_literal', 'raw_string_literal'].includes(t)) {
                const literalInfo: Literal = {
                    type: t,
                    value: src.slice(n.startIndex, n.endIndex).toString('utf8'),
                    filePath: filePath,
                    span: {
                        startLine: n.startPosition.row + 1,
                        endLine: n.endPosition.row + 1,
                        startByte: n.startIndex,
                        endByte: n.endIndex
                    }
                };
                comp.literals.push(literalInfo);
            } else if (t === 'let_declaration') {
                const pat = n.childForFieldName('pattern');
                const init = n.childForFieldName('value');
                const typeNode = n.childForFieldName('type');
                if (pat) {
                    const varInfo: Variable = {
                        name: src.slice(pat.startIndex, pat.endIndex).toString('utf8'),
                        type: this.extractTypeInfo(typeNode, src),
                        value: init ? src.slice(init.startIndex, init.endIndex).toString('utf8') : null,
                        filePath: filePath,
                        span: {
                            startLine: n.startPosition.row + 1,
                            endLine: n.endPosition.row + 1,
                            startByte: n.startIndex,
                            endByte: n.endIndex
                        }
                    };
                    comp.variables.push(varInfo);
                }
            } else if (['type_identifier', 'primitive_type', 'generic_type', 'scoped_type_identifier'].includes(t)) {
                const typeText = src.slice(n.startIndex, n.endIndex).toString('utf8');
                const resolvedType = this.resolveSymbolPath(typeText);
                const typeInfo: TypeUsed = {
                    type: typeText,
                    resolvedType: resolvedType
                };
                if (!comp.typesUsed.some(existing => existing.type === typeText)) {
                    comp.typesUsed.push(typeInfo);
                }
            } else if (t === 'lifetime') {
                const lifetimeText = src.slice(n.startIndex, n.endIndex).toString('utf8');
                if (!comp.lifetimes.includes(lifetimeText)) {
                    comp.lifetimes.push(lifetimeText);
                }
            }
            for (const child of n.namedChildren) {
                walk(child);
            }
        };
        walk(node);
    }
}
