import { SyntaxNode } from 'tree-sitter';
import { DetailedChanges } from './Detailedchanges';
import { BaseFileDiff } from './basefilediff';

export class HaskellFileDiff extends BaseFileDiff {
    private parser: any;

    constructor(moduleName: string = "", parser: any) {
        super(moduleName);
        this.changes = new DetailedChanges(moduleName);
        this.parser = parser;
    }

    getDeclName(node: SyntaxNode): string | null {
        if (node.type === 'instance') {
            const instanceHeadNodes: string[] = [];
            for (const child of node.children) {
                if (child.type === 'where') {
                    break;
                }
                if (child.type !== 'instance') {
                    instanceHeadNodes.push(child.text);
                }
            }
            return instanceHeadNodes.join(" ").trim();
        }

        if (node.type === 'class') {
            for (const child of node.children) {
                if (child.type === 'name') {
                    return child.text;
                }
            }
            for (let i = 0; i < node.children.length; i++) {
                const child = node.children[i];
                if (child.type === 'class' && i + 1 < node.children.length) {
                    const nextChild = node.children[i + 1];
                    if (['name', 'constructor', 'variable'].includes(nextChild.type)) {
                        return nextChild.text;
                    }
                }
            }
        }

        const queue = [...node.children];
        while (queue.length > 0) {
            const current = queue.shift()!;
            if (['variable', 'constructor'].includes(current.type)) {
                return current.text;
            }
            if (current.isNamed) {
                queue.push(...current.children);
            }
        }
        return null;
    }

    extractComponents(root: SyntaxNode): any[] {
        const functions: any = {};
        const data_types: any = {};
        const type_classes: any = {};
        const instances: any = {};
        const imports: any = {};
        const template_haskell: any = {};

        const nodeTypeMap: Record<string, any> = {
            "function": functions,
            "signature": functions,
            "bind": functions,
            "data_type": data_types,
            "class": type_classes,
            "instance": instances,
            "import": imports,
            "top_splice": template_haskell,
        };

        let declarations: SyntaxNode[] = [];
        if (root.type === 'haskell') {
            const declarationsNode = root.children.find(c => c.type === 'declarations');
            if (declarationsNode) {
                declarations = declarationsNode.children;
            }

            const importsNode = root.children.find(c => c.type === 'imports');
            if (importsNode) {
                for (const importChild of importsNode.children) {
                    if (importChild.type === "import") {
                        const name = importChild.text.trim();
                        imports[name] = [importChild, importChild.text, importChild.startPosition, importChild.endPosition];
                    }
                }
            }
        }

        for (const child of declarations) {
            if (child.type in nodeTypeMap && child.type !== "import") {
                const name = this.getDeclName(child);
                if (name) {
                    const targetDict = nodeTypeMap[child.type];
                    if (!targetDict[name]) {
                        targetDict[name] = [child, child.text, child.startPosition, child.endPosition];
                    } else {
                        const [existingNode, existingText, start, end] = targetDict[name];
                        const newText = child.text;
                        let combinedText: string;
                        let newStart: any;
                        let newEnd: any;

                        if (child.type === "signature") {
                            combinedText = newText + "\n" + existingText;
                            newStart = child.startPosition;
                            newEnd = end;
                        } else if (existingNode.type === "signature") {
                            combinedText = existingText + "\n" + newText;
                            newStart = start;
                            newEnd = child.endPosition;
                        } else {
                            combinedText = existingText + "\n" + newText;
                            newStart = start;
                            newEnd = child.endPosition;
                        }
                        targetDict[name] = [child, combinedText, newStart, newEnd];
                    }
                }
            }
        }
        return [functions, data_types, type_classes, instances, imports, template_haskell];
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
            const oldBody = beforeMap[name][1];
            const newBody = afterMap[name][1];
            if (oldBody.trim() !== newBody.trim()) {
                modified.push([name, oldBody, newBody, { old_start: afterMap[name][2], old_end: afterMap[name][3] }]);
            }
        }

        return { added, deleted, modified };
    }

    compareTwoFiles(oldFileAst: SyntaxNode, newFileAst: SyntaxNode): DetailedChanges {
        const [oldFuncs, oldData, oldClasses, oldInstances, oldImports, oldTH] = this.extractComponents(oldFileAst);
        const [newFuncs, newData, newClasses, newInstances, newImports, newTH] = this.extractComponents(newFileAst);

        const categoryMap = {
            "functions": [oldFuncs, newFuncs],
            "dataTypes": [oldData, newData],
            "typeClasses": [oldClasses, newClasses],
            "instances": [oldInstances, newInstances],
            "imports": [oldImports, newImports],
            "templateHaskell": [oldTH, newTH],
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
        const [funcs, data, classes, instances, imports, template_haskell] = this.extractComponents(fileAst);

        const categoryMap = {
            "functions": funcs,
            "dataTypes": data,
            "typeClasses": classes,
            "instances": instances,
            "imports": imports,
            "templateHaskell": template_haskell,
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
