import { writeFileSync } from 'fs';
import * as path from 'path';

// Assuming Component is defined in a types file, e.g., '../types/types'
// If not, we should define it here based on its usage.
interface Component {
    [key: string]: any;
}

interface Node {
    id: string;
    category: string;
    [key: string]: any;
}

interface Edge {
    from: string;
    to: string;
    relation: string;
}

function inferProjectRoot(components: Component[]): string | null {
    const modulePaths = components
        .map(comp => comp.module && path.resolve(comp.module))
        .filter((p): p is string => !!p);

    if (modulePaths.length === 0) {
        return null;
    }

    if (modulePaths.length === 1) {
        return path.dirname(modulePaths[0]);
    }

    const sortedPaths = modulePaths.sort();
    const first = sortedPaths[0].split(path.sep);
    const last = sortedPaths[sortedPaths.length - 1].split(path.sep);
    const len = Math.min(first.length, last.length);

    let i = 0;
    while (i < len && first[i] === last[i]) {
        i++;
    }

    return first.slice(0, i).join(path.sep);
}


function makeNodeId(comp: Component, rootDir: string, currentFile: string): string | null {
    let module = comp.file_path;

    if (!module) {
        module = currentFile || "unknown";
    }

    if ((comp.kind === "method" || comp.kind === "field") && comp.class && comp.name) {
        return `${module}::${comp.class}::${comp.name}`;
    }
    if (comp.kind === "namespace" && comp.name) {
        return `${module}::${comp.name}`;
    }
    if (comp.name) {
        return `${module}::${comp.name}`;
    }
    if (comp.id) {
        return comp.id;
    }
    return null;
}

export function adaptTypeScriptComponents(rawComponents: Component[]): { nodes: Node[], edges: Edge[] } {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    console.log(`Adapting ${rawComponents.length} TypeScript components`);

    let rootDir = "";
    let currentFile = "";

    if (rawComponents.length > 0) {
        const first = rawComponents[0];
        rootDir = first.root_folder || "";
        currentFile = first.file_path || "";
    }

    const importMap: { [module: string]: { [alias: string]: [string, string] } } = {};

    // 1. Build import map
    for (const comp of rawComponents) {
        if (comp.kind === "import") {
            const module = comp.module;
            const stmt = comp.code;
            const moduleDir = path.dirname(module);

            if (!importMap[module]) {
                importMap[module] = {};
            }

            // Named imports: import { A, B as C } from './foo'
            let m = stmt.match(/import\s+{([^}]+)}\s+from\s+['"](.+)['"]/);
            if (m) {
                const names = m[1];
                const src = m[2];
                const srcPath = path.normalize(path.join(moduleDir, src + ".ts")).replace(/\\/g, "/");
                for (const name of names.split(",")) {
                    const trimmedName = name.trim();
                    if (trimmedName.includes(" as ")) {
                        const [orig, alias] = trimmedName.split(" as ").map(n => n.trim());
                        importMap[module][alias] = [srcPath, orig];
                    } else {
                        importMap[module][trimmedName] = [srcPath, trimmedName];
                    }
                }
                continue;
            }

            // Default import: import A from './foo'
            m = stmt.match(/import\s+([a-zA-Z0-9_$]+)\s+from\s+['"](.+)['"]/);
            if (m) {
                const name = m[1];
                const src = m[2];
                const srcPath = path.normalize(path.join(moduleDir, src + ".ts")).replace(/\\/g, "/");
                importMap[module][name] = [srcPath, "default"];
                continue;
            }

            // Namespace import: import * as A from './foo'
            m = stmt.match(/import\s+\*\s+as\s+([a-zA-Z0-9_$]+)\s+from\s+['"](.+)['"]/);
            if (m) {
                const ns = m[1];
                const src = m[2];
                const srcPath = path.normalize(path.join(moduleDir, src + ".ts")).replace(/\\/g, "/");
                importMap[module][ns] = [srcPath, "*"];
            }
        }
    }

    const existingNodes = new Set<string>();

    for (const comp of rawComponents) {
        const kind = comp.kind;
        const nodeId = makeNodeId(comp, rootDir, currentFile);

        if (!nodeId || existingNodes.has(nodeId)) {
            continue;
        }

        const category = kind !== "namespace" ? kind : "namespace";

        const node: Partial<Node> = {
            id: nodeId,
            category: category,
            signature: comp.type_signature,
            type_parameters: comp.type_parameters,
            type_parameters_structured: comp.type_parameters_structured,
            utility_type: comp.utility_type,
            parameters: comp.parameters,
            decorators: comp.decorators,
            location: {
                start: comp.start_line,
                end: comp.end_line,
                module: comp.module,
            },
            value: kind === "variable" ? comp.value : undefined,
            bases: kind === "class" ? comp.bases : undefined,
            implements: kind === "class" ? comp.implements : undefined,
            extends: kind === "interface" ? comp.extends : undefined,
            members: comp.members,
            static: comp.static,
            abstract: comp.abstract,
            readonly: comp.readonly,
            override: comp.override,
            getter: comp.getter,
            setter: comp.setter,
            type_param_constraints: comp.type_param_constraints,
            index_signatures: comp.index_signatures,
        };

        const finalNode = Object.fromEntries(Object.entries(node).filter(([_, v]) => v !== null && v !== undefined));
        nodes.push(finalNode as Node);
        existingNodes.add(nodeId);

        if ((comp.operator === "typeof" || comp.operator === "keyof") && comp.id) {
            const opNodeId = comp.id;
            if (!existingNodes.has(opNodeId)) {
                nodes.push({
                    id: opNodeId,
                    category: comp.operator,
                    label: `${comp.operator} ${comp.target}`,
                    target: comp.target,
                    deps: comp.deps,
                    ast_type: comp.ast_type,
                });
                existingNodes.add(opNodeId);
            }
        }

        if (kind === "type_alias" && comp.utility_type) {
            const aliasId = makeNodeId(comp, rootDir, currentFile);
            const ut = comp.utility_type;
            const utilityNodeId = `utility::${ut.utility_type}`;

            if (!existingNodes.has(utilityNodeId)) {
                nodes.push({
                    id: utilityNodeId,
                    category: "utility_type",
                    utility_type: ut.utility_type
                });
                existingNodes.add(utilityNodeId);
            }

            if (aliasId) {
                edges.push({
                    from: aliasId,
                    to: utilityNodeId,
                    relation: "utility_type"
                });
            }

            for (const arg of ut.args) {
                const argId = arg.includes("::") ? arg : `${comp.module}::${arg}`;
                if (!existingNodes.has(argId)) {
                    nodes.push({
                        id: argId,
                        category: "type"
                    });
                    existingNodes.add(argId);
                }
                edges.push({
                    from: utilityNodeId,
                    to: argId,
                    relation: "utility_argument"
                });
            }
        }
    }

    for (const comp of rawComponents) {
        const fromId = makeNodeId(comp, rootDir, currentFile);
        if (!fromId) continue;

        if (comp.kind === "class" && comp.bases) {
            for (const base of comp.bases) {
                const toId = `${comp.module}::${base}`;
                edges.push({ from: fromId, to: toId, relation: "extends" });
            }
        }

        if (comp.kind === "interface" && comp.extends) {
            for (const base of comp.extends) {
                const toId = `${comp.module}::${base}`;
                edges.push({ from: fromId, to: toId, relation: "extends" });
            }
        }

        if (comp.kind === "class" && comp.implements) {
            for (const iface of comp.implements) {
                const toId = `${comp.module}::${iface}`;
                edges.push({ from: fromId, to: toId, relation: "implements" });
            }
        }

        const callableKinds = ["function", "method", "variable", "function_call", "arrow_function", "generator_function", "generator_function_declaration"];
        if (callableKinds.includes(comp.kind) && comp.function_calls) {
            const callerModule = fromId.split("::", 1)[0];
            const callerDir = path.dirname(callerModule);

            for (const call of comp.function_calls) {
                let targetId = call.resolved_callee;
                if (!targetId) {
                    continue;
                }

                if (targetId.startsWith(".")) {
                    const parts = targetId.split("::");
                    if (parts.length === 2) {
                        const [targetFile, targetSymbol] = parts;
                        const combined = path.normalize(path.join(callerDir, targetFile)).replace(/\\/g, "/");
                        targetId = `${combined}::${targetSymbol}`;
                    }
                }

                if (fromId !== targetId) {
                    edges.push({
                        from: fromId,
                        to: targetId,
                        relation: "calls"
                    });
                }
            }
        }

        if (comp.kind === "type_alias" && comp.type_dependencies) {
            for (const dep of comp.type_dependencies) {
                const toId = `${comp.module}::${dep}`;
                if (fromId !== toId) {
                    edges.push({ from: fromId, to: toId, relation: "type_dependency" });
                }
            }
        }

        if ((comp.operator === "typeof" || comp.operator === "keyof") && comp.deps) {
            for (const dep of comp.deps) {
                const toId = dep.includes("::") ? dep : `${comp.module}::${dep}`;
                if (fromId !== toId) {
                    edges.push({ from: fromId, to: toId, relation: "fdeps" });
                }
            }
        }
    }

    const filteredEdges = edges.filter(e => e.from && e.to);
    // writeFileSync("/Users/pramod.p/codetraverse/tmp.txt", JSON.stringify({ nodes, edges: filteredEdges }, null, 2));
    return {
        nodes,
        edges: filteredEdges
    };
}
