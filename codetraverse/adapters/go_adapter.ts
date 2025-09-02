interface RawComponent {
    kind: string;
    name?: string;
    parameters?: string[];
    parameter_types?: { [key: string]: string };
    return_type?: string;
    receiver_type?: string;
    aliased_type?: string;
    type?: string;
    value?: string;
    complete_function_path?: string;
    file_path?: string;
    module?: string;
    start_line?: number;
    end_line?: number;
    location?: { start?: number; end?: number };
    function_calls?: string[];
    type_dependencies?: string[];
    field_types?: string[];
    methods?: string[];
}

interface Node {
    id: string;
    category: string;
    signature: string;
    module: string;
    location: {
        start?: number;
        end?: number;
    };
}

interface Edge {
    from: string;
    to: string;
    relation: string;
}

function signatureFor(comp: RawComponent): string {
    const kind = comp.kind;
    const name = comp.name || "";

    switch (kind) {
        case "function":
        case "method": {
            const params = comp.parameters || [];
            const paramTypes = comp.parameter_types || {};
            const paramsSig = params.map(p => `${p} ${paramTypes[p] || ''}`).join(", ");
            let sig = `func ${name}(${paramsSig})`;
            if (comp.return_type) {
                sig += ` ${comp.return_type}`;
            }
            if (kind === "method" && comp.receiver_type) {
                sig = `func (${comp.receiver_type}) ${sig}`;
            }
            return sig;
        }
        case "struct":
            return `struct ${name}`;
        case "interface":
            return `interface ${name}`;
        case "type_alias":
            return `type ${name} = ${comp.aliased_type}`;
        case "constant":
            return `const ${name} ${comp.type || ''} = ${comp.value || ''}`;
        case "variable":
            return `var ${name} ${comp.type || ''} = ${comp.value || ''}`;
        default:
            return name || "unknown";
    }
}

export function adaptGoComponents(rawComponents: RawComponent[]): { nodes: Node[], edges: Edge[] } {
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    const idSet = new Set<string>();
    const funcLookup: { [key: string]: string[] } = {};

    // 1. Build NODES and func_lookup
    for (const comp of rawComponents) {
        if (comp.kind === "file") continue;

        let nodeId = comp.complete_function_path;
        if (!nodeId) {
            const name = comp.name;
            const fallbackPath = (comp.file_path || "").replace(/\//g, "::").replace(/\\/g, "::");
            nodeId = name ? `${fallbackPath}::${name}` : undefined;
        }

        if (!nodeId || idSet.has(nodeId)) continue;
        idSet.add(nodeId);

        const node: Node = {
            id: nodeId,
            category: comp.kind,
            signature: signatureFor(comp),
            module: comp.module || comp.file_path || "",
            location: {
                start: comp.start_line || comp.location?.start,
                end: comp.end_line || comp.location?.end,
            }
        };
        nodes.push(node);

        if (["function", "method"].includes(comp.kind)) {
            const key = `${comp.name || ""},${comp.file_path || ""}`;
            if (!funcLookup[key]) {
                funcLookup[key] = [];
            }
            funcLookup[key].push(nodeId);
        }
    }

    // 1.5. Create simplified alias nodes
    const aliasNodes: Node[] = [];
    const aliasEdges: Edge[] = [];
    for (const comp of rawComponents) {
        if (!["function", "method", "struct", "interface", "type_alias", "constant", "variable"].includes(comp.kind)) {
            continue;
        }

        const originalId = comp.complete_function_path;
        if (!originalId || !originalId.includes("::")) continue;

        const parts = originalId.split("::");
        if (parts.length >= 2) {
            const filePath = parts[0];
            const funcName = parts[1];
            const pkg = filePath.includes('/') ? filePath.split('/')[0] : (filePath.endsWith('.go') ? filePath.slice(0, -3) : filePath);
            const aliasId = `${pkg}::${funcName}`;

            if (aliasId !== originalId && !nodes.some(n => n.id === aliasId)) {
                aliasNodes.push({
                    id: aliasId,
                    category: comp.kind,
                    signature: signatureFor(comp),
                    module: pkg,
                    location: {
                        start: comp.start_line || comp.location?.start,
                        end: comp.end_line || comp.location?.end,
                    }
                });
                aliasEdges.push({ from: aliasId, to: originalId, relation: "alias_of" });
            }
        }
    }
    nodes.push(...aliasNodes);

    // 2. Build EDGES
    for (const comp of rawComponents) {
        if (comp.kind === "file") continue;

        let fromId = comp.complete_function_path;
        if (!fromId) {
            const name = comp.name;
            const fallbackPath = (comp.file_path || "").replace(/\//g, "::").replace(/\\/g, "::");
            fromId = name ? `${fallbackPath}::${name}` : undefined;
        }

        if (!fromId) continue;

        if (["function", "method"].includes(comp.kind)) {
            for (const call of comp.function_calls || []) {
                let toIds: string[] = [];
                const keyWithFile = `${call},${comp.file_path || ""}`;
                const keyWithoutFile = `${call},`;

                if (funcLookup[keyWithFile]) {
                    toIds = funcLookup[keyWithFile];
                } else if (funcLookup[keyWithoutFile]) {
                    toIds = funcLookup[keyWithoutFile];
                } else {
                    toIds = Object.entries(funcLookup)
                        .filter(([key]) => key.startsWith(`${call},`))
                        .flatMap(([, ids]) => ids);
                }

                for (const toId of toIds) {
                    edges.push({ from: fromId, to: toId, relation: "calls" });
                }
            }
            for (const dep of comp.type_dependencies || []) {
                if (dep) edges.push({ from: fromId, to: dep, relation: "uses_type" });
            }
            if (comp.kind === "method" && comp.receiver_type) {
                edges.push({ from: comp.receiver_type, to: fromId, relation: "has_method" });
            }
        } else if (comp.kind === "struct") {
            for (const fieldType of comp.field_types || []) {
                if (fieldType) edges.push({ from: fromId, to: fieldType, relation: "field_type" });
            }
            for (const m of comp.methods || []) {
                const key = `${m},${comp.file_path || ""}`;
                const mIds = funcLookup[key] || Object.entries(funcLookup)
                    .filter(([k]) => k.startsWith(`${m},`))
                    .flatMap(([, ids]) => ids);
                for (const mId of mIds) {
                    edges.push({ from: fromId, to: mId, relation: "has_method" });
                }
            }
        } else if (comp.kind === "interface") {
            for (const dep of comp.type_dependencies || []) {
                if (dep) edges.push({ from: fromId, to: dep, relation: "interface_dep" });
            }
        } else if (comp.kind === "type_alias") {
            if (comp.aliased_type) {
                edges.push({ from: fromId, to: comp.aliased_type, relation: "type_alias" });
            }
        } else if (["constant", "variable"].includes(comp.kind)) {
            if (comp.type) {
                edges.push({ from: fromId, to: comp.type, relation: "var_type" });
            }
        }
    }

    // 3. Add nodes for missing edge endpoints
    for (const edge of edges) {
        for (const end of [edge.from, edge.to]) {
            if (end && !idSet.has(end)) {
                nodes.push({
                    id: end,
                    category: "unknown",
                    module: end.includes("::") ? end.split("::")[0] : "unknown",
                    signature: "",
                    location: {}
                });
                idSet.add(end);
            }
        }
    }

    // 4. Add alias edges
    edges.push(...aliasEdges);

    return { nodes, edges };
}
