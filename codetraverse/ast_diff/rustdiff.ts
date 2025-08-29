import { SyntaxNode } from 'tree-sitter';
import { DetailedChanges } from './Detailedchanges';
import { BaseFileDiff } from './basefilediff';

export class RustFileDiff extends BaseFileDiff {
    constructor(moduleName: string = "") {
        super(moduleName);
        this.changes = new DetailedChanges(moduleName);
    }

    getDeclName(node: SyntaxNode): string | null {
        if (node.type === 'impl_item') {
            const traitNode = node.childForFieldName('trait');
            const typeNode = node.childForFieldName('type');
            if (traitNode && typeNode) {
                return `${traitNode.text} for ${typeNode.text}`;
            } else if (typeNode) {
                return typeNode.text;
            }
        }

        if (node.type === 'use_declaration') {
            const argNode = node.childForFieldName('argument');
            if (argNode) {
                return argNode.text;
            }
        }

        const nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }
        return null;
    }

    extractComponents(root: SyntaxNode): any {
        const items = {
            "functions": {}, "structs": {}, "enums": {}, "traits": {},
            "impls": {}, "uses": {}, "consts": {},
        };

        const nodeTypeMap: Record<string, any> = {
            "function_item": items.functions,
            "struct_item": items.structs,
            "enum_item": items.enums,
            "trait_item": items.traits,
            "impl_item": items.impls,
            "use_declaration": items.uses,
            "const_item": items.consts,
            "static_item": items.consts,
            "type_item": items.structs,
        };

        if (root.type === 'source_file') {
            for (const child of root.children) {
                if (child.type in nodeTypeMap) {
                    const name = this.getDeclName(child);
                    if (name) {
                        const targetDict = nodeTypeMap[child.type];
                        targetDict[name] = [child, child.text, child.startPosition, child.endPosition];
                    }
                }
            }
        }
        return items;
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
        const oldItems = this.extractComponents(oldFileAst);
        const newItems = this.extractComponents(newFileAst);

        for (const category of ["functions", "structs", "enums", "traits", "impls", "uses", "consts"]) {
            const diff = this.diffComponents(oldItems[category], newItems[category]);
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
