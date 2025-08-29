import { SyntaxNode } from 'tree-sitter';
import { DetailedChanges } from './Detailedchanges';
import { BaseFileDiff } from './basefilediff';

export class TypeScriptFileDiff extends BaseFileDiff {
    constructor(moduleName: string = "") {
        super(moduleName);
        this.changes = new DetailedChanges(moduleName);
    }

    getDeclName(node: SyntaxNode): string | null {
        if (node.type === 'export_statement') {
            if (node.namedChildCount > 0) {
                const declarationNode = node.namedChildren[node.namedChildren.length - 1];
                if (declarationNode) {
                    return this.getDeclName(declarationNode);
                }
            }
        }

        if (node.type === 'lexical_declaration') {
            const declaratorNode = node.namedChildren[0];
            if (declaratorNode && declaratorNode.type === 'variable_declarator') {
                const nameNode = declaratorNode.childForFieldName('name');
                if (nameNode) {
                    return nameNode.text;
                }
            }
        }

        const nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }

        return null;
    }

    extractClassMethods(classNode: SyntaxNode, className: string, functionsDict: any, fieldsDict: any) {
        const classBody = classNode.children.find(c => c.type === 'class_body');
        if (!classBody) {
            return;
        }

        for (const child of classBody.children) {
            if (child.type === 'method_definition') {
                const methodNameNode = child.childForFieldName('name');
                if (methodNameNode) {
                    const methodName = methodNameNode.text;
                    const qualifiedName = `${className}.${methodName}`;
                    functionsDict[qualifiedName] = [child, child.text, child.startPosition, child.endPosition];
                }
            } else if (child.type === 'public_field_definition') {
                const fieldNameNode = child.childForFieldName('name');
                if (fieldNameNode) {
                    const fieldName = fieldNameNode.text;
                    const qualifiedName = `${className}.${fieldName}`;
                    fieldsDict[qualifiedName] = [child, child.text, child.startPosition, child.endPosition];
                }
            }
        }
    }

    extractComponents(root: SyntaxNode): any[] {
        const functions: any = {};
        const classes: any = {};
        const interfaces: any = {};
        const types: any = {};
        const enums: any = {};
        const constants: any = {};
        const fields: any = {};

        const nodeTypeMap: Record<string, any> = {
            'function_declaration': functions,
            'class_declaration': classes,
            'interface_declaration': interfaces,
            'type_alias_declaration': types,
            'enum_declaration': enums,
        };

        const declarations = root.type === 'program' ? root.children : [];

        for (const child of declarations) {
            let nodeToProcess = child;

            if (child.type === 'export_statement') {
                if (child.namedChildCount > 0) {
                    const declarationNode = child.namedChildren[child.namedChildren.length - 1];
                    if (declarationNode) {
                        nodeToProcess = declarationNode;
                    }
                }
            }

            const nodeType = nodeToProcess.type;

            if (nodeType === 'lexical_declaration') {
                const declarator = nodeToProcess.namedChildren[0];
                if (declarator && declarator.type === 'variable_declarator') {
                    const name = this.getDeclName(child);
                    const valueNode = declarator.childForFieldName('value');

                    if (name && valueNode) {
                        let actualValueNode = valueNode;
                        if (actualValueNode.type === 'as_expression' && actualValueNode.childCount > 0) {
                            actualValueNode = actualValueNode.children[0];
                        }

                        if (actualValueNode.type === 'arrow_function') {
                            functions[name] = [child, child.text, child.startPosition, child.endPosition];
                        } else if (actualValueNode.type === 'object') {
                            constants[name] = [child, child.text, child.startPosition, child.endPosition];
                            for (const pairNode of actualValueNode.children) {
                                if (pairNode.type === 'pair') {
                                    const keyNode = pairNode.childForFieldName('key');
                                    const valNode = pairNode.childForFieldName('value');
                                    if (keyNode && valNode && valNode.type === 'arrow_function') {
                                        const innerFuncName = `${name}.${keyNode.text}`;
                                        functions[innerFuncName] = [pairNode, pairNode.text, pairNode.startPosition, pairNode.endPosition];
                                    }
                                }
                            }
                        } else {
                            constants[name] = [child, child.text, child.startPosition, child.endPosition];
                        }
                    }
                }
            } else if (nodeType in nodeTypeMap) {
                const name = this.getDeclName(child);
                if (name) {
                    const targetDict = nodeTypeMap[nodeType];
                    targetDict[name] = [child, child.text, child.startPosition, child.endPosition];
                    if (nodeType === 'class_declaration') {
                        this.extractClassMethods(nodeToProcess, name, functions, fields);
                    }
                }
            }
        }
        return [functions, classes, interfaces, types, enums, constants, fields];
    }

    diffComponents(beforeMap: any, afterMap: any): any {
        const beforeNames = new Set(Object.keys(beforeMap));
        const afterNames = new Set(Object.keys(afterMap));

        const addedNames = Array.from(afterNames).filter(name => !beforeNames.has(name));
        const deletedNames = Array.from(beforeNames).filter(name => !afterNames.has(name));
        const commonNames = Array.from(beforeNames).filter(name => afterNames.has(name));

        const added = addedNames.sort().map(n => [n, afterMap[n][1], { start: afterMap[n][2], end: afterMap[n][3] }]);
        const deleted = deletedNames.sort().map(n => [n, beforeMap[n][1], { start: beforeMap[n][2], end: beforeMap[n][3] }]);

        const modified = [];
        for (const name of commonNames.sort()) {
            const [oldAst, oldBody, oldStart, oldEnd] = beforeMap[name];
            const [newAst, newBody, newStart, newEnd] = afterMap[name];
            if (oldBody.trim() !== newBody.trim()) {
                modified.push([name, oldBody, newBody, { old_start: oldStart, old_end: oldEnd, new_start: newStart, new_end: newEnd }]);
            }
        }

        return { added, deleted, modified };
    }

    compareTwoFiles(oldFileAst: SyntaxNode, newFileAst: SyntaxNode): DetailedChanges {
        const [oldFuncs, oldClasses, oldIfaces, oldTypes, oldEnums, oldConsts, oldFields] = this.extractComponents(oldFileAst);
        const [newFuncs, newClasses, newIfaces, newTypes, newEnums, newConsts, newFields] = this.extractComponents(newFileAst);

        const categoryMap = {
            "functions": [oldFuncs, newFuncs],
            "classes": [oldClasses, newClasses],
            "interfaces": [oldIfaces, newIfaces],
            "types": [oldTypes, newTypes],
            "enums": [oldEnums, newEnums],
            "constants": [oldConsts, newConsts],
            "fields": [oldFields, newFields],
        };

        for (const category in categoryMap) {
            const [oldMap, newMap] = categoryMap[category as keyof typeof categoryMap];
            const diff = this.diffComponents(oldMap, newMap);
            for (const changeType in diff) {
                for (const item of diff[changeType]) {
                    this.changes.add_change(category, changeType, item);
                }
            }
        }

        return this.changes;
    }

    processSingleFile(fileAst: SyntaxNode, mode: string = "deleted"): DetailedChanges {
        const [funcs, classes, interfaces, types, enums, consts, fields] = this.extractComponents(fileAst);

        const categoryMap = {
            "functions": funcs,
            "classes": classes,
            "interfaces": interfaces,
            "types": types,
            "enums": enums,
            "constants": consts,
            "fields": fields,
        };

        for (const category in categoryMap) {
            const componentMap = categoryMap[category as keyof typeof categoryMap];
            for (const name in componentMap) {
                const dataTuple = componentMap[name];
                const item = [name, dataTuple[1], { start: dataTuple[2], end: dataTuple[3] }];
                this.changes.add_change(category, mode, item);
            }
        }

        return this.changes;
    }
}
