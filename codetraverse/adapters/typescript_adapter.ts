import * as path from 'path';
import { Component } from '../types/types';

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

function makeNodeId(comp: Component, file_path: string): string | null {
    const module = file_path;
    if (!module) {
        return null;
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
    const existingNodes = new Set<string>();

    for (const comp of rawComponents) {
        const kind = comp.kind;
        const node_id = makeNodeId(comp, comp.file_path || "");

        if (!node_id || existingNodes.has(node_id)) {
            continue;
        }

        const category = kind !== "namespace" ? kind : "namespace";

        const node: Node = {
            id: node_id,
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
            value: comp.kind === "variable" ? comp.value : undefined,
            bases: comp.kind === "class" ? comp.bases : undefined,
            implements: comp.kind === "class" ? comp.implements : undefined,
            extends: comp.kind === "interface" ? comp.extends : undefined,
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

        Object.keys(node).forEach(key => node[key] === undefined && delete node[key]);
        nodes.push(node);
        existingNodes.add(node_id);

        if ((comp.operator === "typeof" || comp.operator === "keyof") && comp.id) {
            const op_node_id = comp.id;
            if (!existingNodes.has(op_node_id)) {
                nodes.push({
                    id: op_node_id,
                    category: comp.operator,
                    label: `${comp.operator} ${comp.target}`,
                    target: comp.target,
                    deps: comp.deps,
                    ast_type: comp.ast_type,
                });
                existingNodes.add(op_node_id);
            }
        }

        if (comp.kind === "type_alias" && comp.utility_type) {
            const alias_id = makeNodeId(comp, comp.file_path || "");
            const ut = comp.utility_type;
            const utility_node_id = `utility::${ut.utility_type}`;

            if (!existingNodes.has(utility_node_id)) {
                nodes.push({
                    id: utility_node_id,
                    category: "utility_type",
                    utility_type: ut.utility_type
                });
                existingNodes.add(utility_node_id);
            }

            if (alias_id) {
                edges.push({
                    from: alias_id,
                    to: utility_node_id,
                    relation: "utility_type"
                });
            }

            for (const arg of ut.args) {
                const arg_id = arg.includes("::") ? arg : `${comp.module}::${arg}`;
                if (!existingNodes.has(arg_id)) {
                    nodes.push({
                        id: arg_id,
                        category: "type"
                    });
                    existingNodes.add(arg_id);
                }
                edges.push({
                    from: utility_node_id,
                    to: arg_id,
                    relation: "utility_argument"
                });
            }
        }
    }

    for (const comp of rawComponents) {
        const from_id = makeNodeId(comp, comp.file_path || "");
        if (!from_id) continue;

        if (comp.kind === "class" && comp.bases) {
            for (const base of comp.bases) {
                const to_id = `${comp.module}::${base}`;
                edges.push({ from: from_id, to: to_id, relation: "extends" });
            }
        }

        if (comp.kind === "interface" && comp.extends) {
            for (const base of comp.extends) {
                const to_id = `${comp.module}::${base}`;
                edges.push({ from: from_id, to: to_id, relation: "extends" });
            }
        }

        if (comp.kind === "class" && comp.implements) {
            for (const iface of comp.implements) {
                const to_id = `${comp.module}::${iface}`;
                edges.push({ from: from_id, to: to_id, relation: "implements" });
            }
        }

        if (["function", "method", "variable", "function_call", "arrow_function", "generator_function", "generator_function_declaration"].includes(comp.kind || "") && comp.function_calls) {
            const caller_module = from_id.split("::")[0];
            const caller_dir = path.dirname(caller_module);

            for (const call of comp.function_calls) {
                let target_id = call.resolved_callee;
                if (!target_id) continue;

                if (target_id.startsWith(".")) {
                    const [target_file, target_symbol] = target_id.split("::");
                    if (target_file && target_symbol) {
                        const from_file = caller_module;
                        const from_dir = path.dirname(from_file);
                        const combined = path.normalize(path.join(from_dir, target_file)).replace(/\\/g, "/");
                        target_id = `${combined}::${target_symbol}`;
                    }
                }

                if (from_id !== target_id) {
                    edges.push({ from: from_id, to: target_id, relation: "calls" });
                }
            }
        }

        if (comp.kind === "type_alias" && comp.type_dependencies) {
            for (const dep of comp.type_dependencies) {
                const to_id = `${comp.module}::${dep}`;
                if (from_id !== to_id) {
                    edges.push({ from: from_id, to: to_id, relation: "type_dependency" });
                }
            }
        }

        if ((comp.operator === "typeof" || comp.operator === "keyof") && comp.deps) {
            for (const dep of comp.deps) {
                const to_id = dep.includes("::") ? dep : `${comp.module}::${dep}`;
                if (from_id !== to_id) {
                    edges.push({ from: from_id, to: to_id, relation: "fdeps" });
                }
            }
        }
    }

    const filtered_edges = edges.filter(e => e.from && e.to);
    return { nodes, edges: filtered_edges };
}
