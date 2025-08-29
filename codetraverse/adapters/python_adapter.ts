import * as path from 'path';

interface RawComponent {
    module?: string;
    file_path?: string;
    kind: string;
    class?: string;
    name?: string;
    start_line?: number;
    end_line?: number;
    decorators?: any; // Adjust type as needed
    parameters?: any; // Adjust type as needed
    returns?: any;    // Adjust type as needed
    annotation?: any; // Adjust type as needed
    bases?: string[];
    function_calls?: { resolved_callee?: string }[];
    imported?: string;
    from?: string;
}

interface Node {
    id: string;
    category: string;
    decorators?: any;
    parameters?: any;
    returns?: any;
    annotation?: any;
    location?: { // Made optional as it can be removed if empty
        start?: number;
        end?: number;
        module?: string;
    };
}

interface Edge {
    from: string;
    to: string;
    relation: string;
}

export interface AdaptedComponents {
    nodes: Node[];
    edges: Edge[];
}

export function inferProjectRoot(components: RawComponent[]): string | null {
    const paths = components
        .filter(comp => comp.module)
        .map(comp => path.resolve(comp.module!));

    if (!paths.length) {
        return null;
    }

    // A simple common path implementation.
    // For a more robust solution, consider a dedicated library or more complex logic.
    const pathSegments = paths.map(p => p.split(path.sep).filter(s => s !== ''));

    if (pathSegments.length === 0) {
        return null;
    }

    let commonPrefix: string[] = [];
    const firstPath = pathSegments[0];

    for (let i = 0; i < firstPath.length; i++) {
        const segment = firstPath[i];
        let allMatch = true;
        for (let j = 1; j < pathSegments.length; j++) {
            if (i >= pathSegments[j].length || pathSegments[j][i] !== segment) {
                allMatch = false;
                break;
            }
        }
        if (allMatch) {
            commonPrefix.push(segment);
        } else {
            break;
        }
    }
    // path.join handles leading slash correctly for root directories
    return path.join(...commonPrefix);
}

export function makeNodeId(comp: RawComponent): string {
    const module = comp.file_path || comp.module || process.env.CURRENT_FILE || "<unknown>";
    const kind = comp.kind;

    if (["method", "async_method"].includes(kind) && comp.class && comp.name) {
        return `${module}::${comp.class}.${comp.name}`;
    } else if (["lambda", "yield", "list_comprehension", "set_comprehension", "dict_comprehension", "generator_expression"].includes(kind)) {
        return `${module}::${kind}.${comp.start_line}`;
    } else if (comp.name) {
        return `${module}::${comp.name}`;
    }
    // fallback
    return `${module}::${kind}.${comp.start_line}`;
}

export function adaptPythonComponents(rawComponents: RawComponent[]): AdaptedComponents {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    if (rawComponents.length > 0) {
        const pr = inferProjectRoot(rawComponents);
        process.env.ROOT_DIR = pr || '';
        process.env.CURRENT_FILE = rawComponents[0].module || '';
    }

    const existing = new Set<string>();

    // build import map
    const importMap: { [key: string]: { [key: string]: string } } = {};
    for (const comp of rawComponents) {
        if (comp.kind === "import" && comp.name && comp.from) {
            const mod = comp.file_path;
            if (mod) {
                if (!importMap[mod]) {
                    importMap[mod] = {};
                }
                importMap[mod][comp.name] = comp.from;
            }
        }
    }

    // nodes
    for (const comp of rawComponents) {
        const nid = makeNodeId(comp);
        if (existing.has(nid)) {
            continue;
        }
        existing.add(nid);

        let node: Node = {
            id: nid,
            category: comp.kind,
            decorators: comp.decorators,
            parameters: comp.parameters,
            returns: comp.returns,
            annotation: comp.annotation,
            location: {
                start: comp.start_line,
                end: comp.end_line,
                module: comp.module
            },
        };
        // remove nulls/undefineds from top-level properties
        node = Object.fromEntries(Object.entries(node).filter(([, v]) => v !== undefined && v !== null)) as Node;
        // Special handling for location object to remove nulls/undefineds within it
        if (node.location) {
            node.location = Object.fromEntries(Object.entries(node.location).filter(([, v]) => v !== undefined && v !== null)) as Node['location'];
            if (Object.keys(node.location).length === 0) {
                delete node.location; // Remove location if it becomes empty
            }
        }
        nodes.push(node);
    }

    // inheritance edges
    for (const comp of rawComponents) {
        if (comp.kind === "class" && comp.bases) {
            const fromId = makeNodeId(comp);
            for (const b of comp.bases) {
                const toId = `${comp.file_path}::${b}`;
                edges.push({ from: fromId, to: toId, relation: "extends" });
            }
        }
    }

    // call edges
    for (const comp of rawComponents) {
        if (comp.function_calls) {
            const fromId = makeNodeId(comp);
            for (const call of comp.function_calls) {
                let tgt = call.resolved_callee;
                if (!tgt) continue;

                // if imported
                const parts = tgt.split("::");
                if (parts.length === 2 && comp.file_path && importMap[comp.file_path] && importMap[comp.file_path][parts[1]]) {
                    // always force a .py path here
                    const mod = importMap[comp.file_path][parts[1]];
                    const path_ = mod.replace(/\./g, "/") + ".py";
                    tgt = `${path_}::${parts[1]}`;
                }
                if (fromId !== tgt) {
                    edges.push({ from: fromId, to: tgt, relation: "calls" });
                }
            }
        }
    }

    // filter empty
    const filteredEdges = edges.filter(e => e.from && e.to);
    return { nodes: nodes, edges: filteredEdges };
}
