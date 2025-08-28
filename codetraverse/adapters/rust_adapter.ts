import { Component, FunctionCall } from '../types/types';

interface Node {
    id: string;
    category: string;
    name: string;
    filePath?: string;
    start?: number;
    end?: number;
}

interface Edge {
    from: string;
    to: string;
    relation: string;
}

export function extractRustId(comp: Component): string {
    const namePart = comp.name || "<unnamed>";
    let modulePart: string;
    if (comp.module) {
        modulePart = comp.module;
    } else {
        modulePart = "<anonymous_module>";
    }
    const lastModuleSegment = modulePart.split('::').pop();
    return `${lastModuleSegment}::${namePart}`;
}

export function buildModulePathForComponent(comp: Component, currentModuleStack: string[] = []): string {
    if (comp.resolved_module_path) {
        return comp.resolved_module_path;
    }
    const name = comp.name || "";
    if (currentModuleStack.length > 0) {
        return [...currentModuleStack, name].join("::");
    } else {
        return name;
    }
}

export function adaptRustComponents(rawComponents: Component[], quiet = true): { nodes: Node[], edges: Edge[] } {
    const nodes: Record<string, Node> = {};
    const edges: Edge[] = [];
    const allComponents: Component[] = [];
    const nameToFqIds: Record<string, string[]> = {};

    const processComponentTree = (comps: Component[], currentModulePath: string[] = [], parentFqId: string | null = null) => {
        for (const comp of comps) {
            const compModulePath = [...currentModulePath];
            if (comp.kind === 'mod_item') {
                compModulePath.push(comp.name || '');
            }
            comp.current_module_path = compModulePath;

            const compType = comp.kind;
            const name = comp.name;
            let fqId: string | null = null;
            if (['function_item', 'struct_item', 'enum_item', 'trait_item', 'impl_item', 'mod_item'].includes(compType)) {
                if (comp.current_module_path && comp.current_module_path.length > 0) {
                    const modulePath = comp.current_module_path.join("::");
                    fqId = `${modulePath}::${name}`;
                } else {
                    fqId = name;
                }
                comp.fq_id = fqId;
                if (name) {
                    if (!nameToFqIds[name]) {
                        nameToFqIds[name] = [];
                    }
                    nameToFqIds[name].push(fqId);
                }

                if (parentFqId && fqId) {
                    edges.push({
                        from: parentFqId,
                        to: fqId,
                        relation: "contains"
                    });
                }
            }
            
            const children = comp.children || [];
            if (children.length > 0) {
                processComponentTree(children, compModulePath, fqId);
            }
            allComponents.push(comp);
        }
    };
    processComponentTree(rawComponents);

    for (const comp of allComponents) {
        const compType = comp.kind;
        if (['function_item', 'struct_item', 'enum_item', 'trait_item', 'impl_item', 'mod_item'].includes(compType)) {
            const fqId = comp.fq_id;
            if (fqId) {
                nodes[fqId] = {
                    id: fqId,
                    category: compType,
                    name: comp.name,
                    filePath: comp.filePath,
                    start: comp.span?.startLine || 0,
                    end: comp.span?.endLine || 0
                };
            }
        }

        const sourceId = comp.fq_id || comp.name || 'unknown';

        for (const call of comp.functionCalls || []) {
            const callName = call.name;
            const resolvedModule = call.modules?.[0];
            let targetId: string | undefined;
            if (resolvedModule && resolvedModule !== callName) {
                targetId = resolvedModule;
            } else {
                targetId = callName;
            }
            if (targetId) {
                edges.push({
                    from: sourceId,
                    to: targetId,
                    relation: "calls"
                });
            }
        }

        for (const call of comp.methodCalls || []) {
            const methodName = call.method;
            const resolvedModule = call.modules?.[0];
            let targetId: string | undefined;
            if (resolvedModule) {
                targetId = resolvedModule;
            } else {
                const receiver = call.receiver || '';
                targetId = receiver ? `${receiver}::${methodName}` : methodName;
            }
            if (targetId) {
                edges.push({
                    from: sourceId,
                    to: targetId,
                    relation: "calls"
                });
            }
        }

        for (const call of comp.macroCalls || []) {
            const macroName = call.name;
            const resolvedModule = call.modules?.[0];
            const targetId = resolvedModule || macroName;
            if (targetId) {
                edges.push({
                    from: sourceId,
                    to: targetId,
                    relation: "calls"
                });
            }
        }

        if (compType === 'use_declaration') {
            for (const importInfo of comp.imports || []) {
                edges.push({
                    from: sourceId,
                    to: importInfo.path,
                    relation: "imports"
                });
            }
        }

        for (const typeInfo of comp.typesUsed || []) {
            let targetId: string | undefined;
            if (typeof typeInfo === 'object' && typeInfo !== null) {
                const typeName = typeInfo.type;
                const resolvedType = typeInfo.resolvedType;
                targetId = resolvedType || typeName;
            } else {
                targetId = String(typeInfo);
            }
            if (targetId) {
                edges.push({
                    from: sourceId,
                    to: targetId,
                    relation: "uses_type"
                });
            }
        }
    }

    const finalNodes = Object.values(nodes);
    const seenIds = new Set(Object.keys(nodes));

    for (const edge of edges) {
        for (const endpointKey of ["from", "to"] as const) {
            const endpointId = edge[endpointKey];
            if (!seenIds.has(endpointId)) {
                let category = "external_reference";
                if (endpointId.includes("::")) {
                    if (edge.relation === "calls") {
                        category = "external_function";
                    } else if (edge.relation === "uses_type") {
                        category = "external_type";
                    } else if (edge.relation === "imports") {
                        category = "external_module";
                    }
                }
                const simpleName = endpointId.split("::").pop() || "";
                finalNodes.push({
                    id: endpointId,
                    category: category,
                    name: simpleName
                });
                seenIds.add(endpointId);
            }
        }
    }

    if (!quiet) {
        console.log(`Created ${len(finalNodes)} nodes and ${len(edges)} edges.`);
    }

    return { nodes: finalNodes, edges: edges };
}

function len(arr: any[]): number {
    return arr.length;
}
