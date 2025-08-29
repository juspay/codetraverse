import { SyntaxNode } from 'tree-sitter';
import { DetailedChanges } from './Detailedchanges';
import { BaseFileDiff } from './basefilediff';

export class GoFileDiff extends BaseFileDiff {
    constructor(moduleName: string = "") {
        super(moduleName);
        this.changes = new DetailedChanges(moduleName);
    }

    getDeclName(node: SyntaxNode): string | null {
        if (node.type === 'method_declaration') {
            const receiver = node.childForFieldName('receiver');
            const name = node.childForFieldName('name');
            if (receiver && name) {
                return `${receiver.text} ${name.text}`;
            }
        }

        const nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }
        return null;
    }

    extractComponents(root: SyntaxNode): any[] {
        const functions: any = {};
        const types: any = {};
        const variables: any = {};
        const constants: any = {};
        const imports: any = {};

        const topLevelTypes = [
            "function_declaration", "method_declaration", "type_declaration",
            "var_declaration", "const_declaration", "import_declaration",
        ];

        if (root.type === 'source_file') {
            for (const child of root.children) {
                if (topLevelTypes.includes(child.type)) {
                    if (child.type === 'import_declaration') {
                        const queue = [...child.children];
                        while (queue.length > 0) {
                            const current = queue.shift()!;
                            if (current.type === 'import_spec') {
                                const pathNode = current.childForFieldName('path');
                                if (pathNode) {
                                    const name = pathNode.text;
                                    imports[name] = [current, current.text, current.startPosition, current.endPosition];
                                }
                            } else {
                                queue.push(...current.children);
                            }
                        }
                    } else if (child.type === 'type_declaration') {
                        for (const typeSpec of child.children) {
                            if (typeSpec.type === 'type_spec') {
                                const name = this.getDeclName(typeSpec);
                                if (name) {
                                    types[name] = [typeSpec, typeSpec.text, typeSpec.startPosition, typeSpec.endPosition];
                                }
                            }
                        }
                    } else if (child.type === 'var_declaration') {
                        for (const varSpec of child.children) {
                            if (varSpec.type === 'var_spec') {
                                for (const nameNode of varSpec.children) {
                                    if (nameNode.type === 'identifier') {
                                        const name = nameNode.text;
                                        variables[name] = [varSpec, varSpec.text, varSpec.startPosition, varSpec.endPosition];
                                    }
                                }
                            }
                        }
                    } else if (child.type === 'const_declaration') {
                        for (const constSpec of child.children) {
                            if (constSpec.type === 'const_spec') {
                                for (const nameNode of constSpec.children) {
                                    if (nameNode.type === 'identifier') {
                                        const name = nameNode.text;
                                        constants[name] = [constSpec, constSpec.text, constSpec.startPosition, constSpec.endPosition];
                                    }
                                }
                            }
                        }
                    } else {
                        const name = this.getDeclName(child);
                        if (name) {
                            functions[name] = [child, child.text, child.startPosition, child.endPosition];
                        }
                    }
                }
            }
        }
        return [functions, types, variables, constants, imports];
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
        const [oldFuncs, oldTypes, oldVars, oldConsts, oldImports] = this.extractComponents(oldFileAst);
        const [newFuncs, newTypes, newVars, newConsts, newImports] = this.extractComponents(newFileAst);

        const categoryMap = {
            "Functions": [oldFuncs, newFuncs],
            "Types": [oldTypes, newTypes],
            "Vars": [oldVars, newVars],
            "Consts": [oldConsts, newConsts],
            "Imports": [oldImports, newImports],
        };

        for (const category in categoryMap) {
            const [oldMap, newMap] = categoryMap[category as keyof typeof categoryMap];
            const diff = this.diffComponents(oldMap, newMap);
            for (const changeType in diff) {
                for (const item of diff[changeType]) {
                    this.changes.add_change(category.toLowerCase(), changeType, item);
                }
            }
        }

        return this.changes;
    }

    processSingleFile(fileAst: SyntaxNode, mode: string = "deleted"): DetailedChanges {
        const [funcs, types, variables, constants, imports] = this.extractComponents(fileAst);

        const categoryMap = {
            "functions": funcs,
            "types": types,
            "vars": variables,
            "consts": constants,
            "imports": imports,
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
