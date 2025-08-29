import { SyntaxNode } from 'tree-sitter';
import { DetailedChanges } from './Detailedchanges';
import { BaseFileDiff } from './basefilediff';

export class PureScriptFileDiff extends BaseFileDiff {
    constructor(moduleName: string = "") {
        super(moduleName);
        this.changes = new DetailedChanges(moduleName);
    }

    getDeclName(node: SyntaxNode): string | null {
        const nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }

        if (node.type === 'function') {
            if (node.childCount > 0 && node.children[0].type === 'identifier') {
                return node.children[0].text;
            }
        }

        if (node.type === 'type_alias_declaration') {
            const tvbNode = node.children.find(c => c.type === 'type_variable_binding');
            if (tvbNode) {
                const nameNode = tvbNode.children.find(c => c.type === 'type_identifier');
                if (nameNode) {
                    return nameNode.text;
                }
            }
        }

        if (node.type === 'foreign_import') {
            const nameNode = node.children.find(c => c.type === 'identifier');
            if (nameNode) {
                return nameNode.text;
            }
        }

        if (node.type === 'class_instance') {
            const instanceNameNode = node.childForFieldName('instance_name');
            if (instanceNameNode) {
                return instanceNameNode.text.trim();
            }
        }

        return null;
    }

    extractComponents(root: SyntaxNode): any {
        const items = {
            "functions": {}, "classes": {}, "data_declarations": {},
            "newtypes": {}, "type_aliases": {}, "foreign_imports": {},
            "instances": {},
        };

        const nodeTypeMap: Record<string, any> = {
            "function": items.functions,
            "class_declaration": items.classes,
            "data_declaration": items.data_declarations,
            "newtype": items.newtypes,
            "type_alias_declaration": items.type_aliases,
            "foreign_import": items.foreign_imports,
            "class_instance": items.instances,
        };

        const queue = [root];
        while (queue.length > 0) {
            const currentNode = queue.shift()!;
            if (currentNode.type in nodeTypeMap) {
                const name = this.getDeclName(currentNode);
                if (name) {
                    const targetDict = nodeTypeMap[currentNode.type];
                    targetDict[name] = [currentNode, currentNode.text, currentNode.startPosition, currentNode.endPosition];
                }
            }

            for (const child of currentNode.children) {
                queue.push(child);
            }
        }

        return items;
    }

    deepEqual(nodeA: SyntaxNode | null, nodeB: SyntaxNode | null): boolean {
        if (!nodeA || !nodeB) {
            return nodeA === nodeB;
        }
        if (nodeA.type !== nodeB.type) {
            return false;
        }

        if (nodeA.children.length === 0) {
            return nodeA.text === nodeB.text;
        }

        if (nodeA.children.length !== nodeB.children.length) {
            return false;
        }

        for (let i = 0; i < nodeA.children.length; i++) {
            if (!this.deepEqual(nodeA.children[i], nodeB.children[i])) {
                return false;
            }
        }

        return true;
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
        const oldItems = this.extractComponents(oldFileAst);
        const newItems = this.extractComponents(newFileAst);

        const allCategories = new Set([...Object.keys(oldItems), ...Object.keys(newItems)]);

        for (const category of Array.from(allCategories)) {
            const oldMap = oldItems[category] || {};
            const newMap = newItems[category] || {};

            const diff = this.diffComponents(oldMap, newMap);

            for (const changeType in diff) {
                for (const data of diff[changeType]) {
                    this.changes.add_change(category, changeType, data);
                }
            }
        }

        return this.changes;
    }

    processSingleFile(fileAst: SyntaxNode, mode: string = "deleted"): DetailedChanges {
        const items = this.extractComponents(fileAst);

        for (const category in items) {
            const componentMap = items[category];
            for (const name in componentMap) {
                const dataTuple = componentMap[name];
                const item = [name, dataTuple[1], { start: dataTuple[2], end: dataTuple[3] }];
                this.changes.add_change(category, mode, item);
            }
        }

        return this.changes;
    }
}
