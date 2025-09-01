import * as fs from 'fs';
import * as jsnx from 'jsnetworkx';
import { buildGraphFromSchema } from './utils/jsnetworkx_graph';

export function loadGraph(graphPath: string): jsnx.Graph | null {
    if (!fs.existsSync(graphPath)) {
        console.error(`Error: Graph file not found at ${graphPath}`);
        return null;
    }
    try {
        const data = JSON.parse(fs.readFileSync(graphPath, 'utf-8'));
        return buildGraphFromSchema(data);
    } catch (e) {
        if (e instanceof Error) {
            console.error(`Error reading or parsing graph file ${graphPath}: ${e.message}`);
        }
        return null;
    }
}

function formatPath(G: jsnx.Graph, path: string[]): string {
    let formatted = "";
    for (let i = 0; i < path.length - 1; i++) {
        const u = path[i];
        const v = path[i + 1];
        const edgeData = G.getEdgeData(u, v);
        const relation = edgeData ? (edgeData as any).relation || "" : "";
        formatted += `${u} --[${relation}]--> `;
    }
    formatted += path[path.length - 1];
    return formatted;
}

export function findFromSingleSource(G: jsnx.Graph, source: string, target: string): string[] {
    return jsnx.shortestPath(G, { source: source, target: target }) as string[];
}

export function findPath(graphPath: string, component: string, source: string | null = null): void {
    const G = loadGraph(graphPath);
    if (!G) {
        return;
    }

    const target = component;

    if (!G.hasNode(target)) {
        console.error(`Error: target '${target}' not in graph.`);
        return;
    }

    if (source) {
        if (!G.hasNode(source)) {
            console.error(`Error: source '${source}' not in graph.`);
            return;
        }
        try {
            const path = findFromSingleSource(G, source, target);
            console.log("  " + formatPath(G, path));
        } catch (e: any) {
            if (e.name === 'NetworkXNoPath') {
                console.log(`No path found from '${source}' to '${target}'.`);
            } else {
                console.error(`An unexpected error occurred: ${e.message}`);
            }
        }
    } else {
        const preds = Array.from(G.predecessors(target));
        const succs = Array.from(G.successors(target));

        if (preds.length > 0) {
            console.log(`\nNodes with edges INTO '${target}' (${preds.length}):`);
            for (const p of preds) {
                const rel = G.getEdgeData(p, target) ? (G.getEdgeData(p, target) as any).relation || "" : "";
                console.log(`  ${p} --[${rel}]--> ${target}`);
            }
        } else {
            console.log(`\nNo incoming edges to '${target}'.`);
        }

        if (succs.length > 0) {
            console.log(`\nNodes with edges OUT OF '${target}' (${succs.length}):`);
            for (const s of succs) {
                const rel = G.getEdgeData(target, s) ? (G.getEdgeData(target, s) as any).relation || "" : "";
                console.log(`  ${target} --[${rel}]--> ${s}`);
            }
        } else {
            console.log(`\nNo outgoing edges from '${target}'.`);
        }
    }
}
