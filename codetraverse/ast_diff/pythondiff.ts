import { SyntaxNode } from 'tree-sitter';
import { DetailedChanges } from './Detailedchanges';
import { BaseFileDiff } from './basefilediff';

export class PythonFileDiff extends BaseFileDiff {
    constructor(moduleName: string = "") {
        super(moduleName);
        this.changes = new DetailedChanges(moduleName);
    }

    getDeclName(node: SyntaxNode): string | null {
        if (node.type === 'decorated_definition') {
            const definition = node.childForFieldName('definition');
            if (definition) {
                return this.getDeclName(definition);
            }
        }

        const nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }

        if (node.type === 'assignment') {
            const leftNode = node.childForFieldName('left');
            if (leftNode && leftNode.type === 'identifier') {
                return leftNode.text;
            }
        }

        return null;
    }

    extractComponents(root: SyntaxNode): any[] {
        const functions: any = {};
        const classes: any = {};
        const imports: any = {};
        const variables: any = {};

        const nodeTypeMap: Record<string, any> = {
            'function_definition': functions,
            'class_definition': classes,
        };

        for (const child of root.children) {
            let nodeToProcess = child;

            if (child.type === 'decorated_definition') {
                const definitionNode = child.childForFieldName('definition');
                if (definitionNode) {
                    nodeToProcess = definitionNode;
                }
            }

            const nodeType = nodeToProcess.type;

            if (nodeType in nodeTypeMap) {
                const name = this.getDeclName(child);
                if (name) {
                    const targetDict = nodeTypeMap[nodeType];
                    targetDict[name] = [child, child.text, child.startPosition, child.endPosition];
                }
            } else if (['import_statement', 'import_from_statement'].includes(nodeType)) {
                const name = child.text;
                imports[name] = [child, name, child.startPosition, child.endPosition];
            } else if (nodeType === 'expression_statement' && child.children[0]?.type === 'assignment') {
                const assignmentNode = child.children[0];
                const name = this.getDeclName(assignmentNode);
                if (name) {
                    variables[name] = [child, child.text, child.startPosition, child.endPosition];
                }
            }
        }
        return [functions, classes, imports, variables];
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
        const [oldFuncs, oldClasses, oldImports, oldVars] = this.extractComponents(oldFileAst);
        const [newFuncs, newClasses, newImports, newVars] = this.extractComponents(newFileAst);

        const categoryMap = {
            "functions": [oldFuncs, newFuncs],
            "classes": [oldClasses, newClasses],
            "imports": [oldImports, newImports],
            "variables": [oldVars, newVars],
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
        const [funcs, classes, imports, variables] = this.extractComponents(fileAst);

        const categoryMap = {
            "functions": funcs,
            "classes": classes,
            "imports": imports,
            "variables": variables,
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
