import { exec } from 'child_process';
import { SyntaxNode } from 'tree-sitter';
import { DetailedChanges } from './Detailedchanges';
import { BaseFileDiff } from './basefilediff';

function formatRescriptFile(filePath: string) {
    try {
        exec(`npx rescript format ${filePath}`);
    } catch (e) {
        // ignore
    }
}

export class RescriptFileDiff extends BaseFileDiff {
    constructor(moduleName: string = "") {
        super(moduleName);
        this.changes = new DetailedChanges(moduleName);
    }

    getDeclName(node: SyntaxNode, nodeType: string | null, nameType: string): string | null {
        for (const child of node.children) {
            if (nodeType && child.type === nodeType) {
                for (const grandchild of child.children) {
                    if (grandchild.isNamed && grandchild.type === nameType) {
                        return grandchild.text;
                    }
                }
            } else if (!nodeType && child.isNamed && child.type === nameType) {
                return child.text;
            }
        }
        return null;
    }

    deepEqual(nodeA: SyntaxNode | null, nodeB: SyntaxNode | null): boolean {
        if (!nodeA || !nodeB) {
            return nodeA === nodeB;
        }

        if (nodeA.type !== nodeB.type) {
            return false;
        }

        const childrenA = nodeA.children;
        const childrenB = nodeB.children;

        if (childrenA.length !== childrenB.length) {
            return false;
        }

        if (childrenA.length === 0) {
            return nodeA.text === nodeB.text && nodeA.parent?.text === nodeB.parent?.text;
        }

        for (let i = 0; i < childrenA.length; i++) {
            if (!this.deepEqual(childrenA[i], childrenB[i])) {
                return false;
            }
        }

        return true;
    }

    extractComponents(root: SyntaxNode): any[] {
        const queue = [root];
        const functions: any = {};
        const types: any = {};
        const externals: any = {};

        const nodeNameMapper: Record<string, [any, (node: SyntaxNode) => string | null]> = {
            "let_declaration": [functions, (x: SyntaxNode) => this.getDeclName(x, "let_binding", "value_identifier")],
            "type_declaration": [types, (x: SyntaxNode) => this.getDeclName(x, "type_binding", "type_identifier")],
            "external_declaration": [externals, (x: SyntaxNode) => this.getDeclName(x, null, "value_identifier")]
        };

        while (queue.length > 0) {
            const currentNode = queue.pop()!;
            if (currentNode.type in nodeNameMapper) {
                const [dct, mapperFunction] = nodeNameMapper[currentNode.type];
                let name = mapperFunction(currentNode);
                if (name) {
                    if (currentNode.parent?.type !== "source_file") {
                        try {
                            name = `${currentNode.parent?.parent?.child(0)?.text}::${name}`;
                        } catch (e) {
                            // ignore
                        }
                    }
                    dct[name] = [currentNode, currentNode.text, currentNode.startPosition, currentNode.endPosition];
                }
            } else {
                for (let i = currentNode.children.length - 1; i >= 0; i--) {
                    const child = currentNode.children[i];
                    if (child.isNamed) {
                        queue.push(child);
                    }
                }
            }
        }
        return [functions, types, externals];
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
            if (!this.deepEqual(oldAst, newAst)) {
                modified.push([name, oldBody, newBody, { old_start: oldStart, old_end: oldEnd, new_start: newStart, new_end: newEnd }]);
            }
        }

        return { added, deleted, modified };
    }

    compareTwoFiles(oldFileAst: SyntaxNode, newFileAst: SyntaxNode): DetailedChanges {
        const [oldFuncs, oldTypes, oldExt] = this.extractComponents(oldFileAst);
        const [newFuncs, newTypes, newExt] = this.extractComponents(newFileAst);

        const categoryMap = {
            "functions": [oldFuncs, newFuncs],
            "types": [oldTypes, newTypes],
            "externals": [oldExt, newExt],
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
        const [funcs, types, exts] = this.extractComponents(fileAst);
        const funcNames = Object.keys(funcs).sort();
        const typeNames = Object.keys(types).sort();
        const extNames = Object.keys(exts).sort();

        if (mode === "deleted") {
            this.changes.changes['deletedFunctions'] = funcNames.map(n => [n, funcs[n][1], { start: funcs[n][2], end: funcs[n][3] }]);
            this.changes.changes['deletedTypes'] = typeNames.map(n => [n, types[n][1], { start: types[n][2], end: types[n][3] }]);
            this.changes.changes['deletedExternals'] = extNames.map(n => [n, exts[n][1], { start: exts[n][2], end: exts[n][3] }]);
        } else {
            this.changes.changes['addedFunctions'] = funcNames.map(n => [n, funcs[n][1], { start: funcs[n][2], end: funcs[n][3] }]);
            this.changes.changes['addedTypes'] = typeNames.map(n => [n, types[n][1], { start: types[n][2], end: types[n][3] }]);
            this.changes.changes['addedExternals'] = extNames.map(n => [n, exts[n][1], { start: exts[n][2], end: exts[n][3] }]);
        }

        return this.changes;
    }
}
