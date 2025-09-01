import * as fs from 'fs';
import * as path from 'path';
import { loadGraph, findFromSingleSource } from '../path'; // Import findFromSingleSource
import { buildCleanGraph } from './jsnetworkx_graph';
import { computeNodeMetrics } from './graph_partitioner';
import { PathResult, NeighborResult } from '@/types/types';

type ModuleInfo = { [key: string]: any };

function parsePathResult(stdout: string): PathResult {
    const lines = stdout.trim().split('\n');

    const pathLine = lines.find(line => line.includes('->'));
    if (pathLine) {
        const parts = pathLine.split('->').map(part => part.trim());
        const pathMatch = parts.length > 1 ? parts : null;

        return {
            found: true,
            path: pathMatch || [],
            message: stdout
        };
    }

    return {
        found: false,
        path: [],
        message: stdout
    };
}

function parseNeighborResult(stdout: string): NeighborResult {
    const lines = stdout.trim().split('\n');
    const incoming: Array<{ from: string; relation: string }> = [];
    const outgoing: Array<{ to: string; relation: string }> = [];

    let section: 'incoming' | 'outgoing' | null = null;

    for (const line of lines) {
        if (line.includes('edges INTO')) {
            section = 'incoming';
            continue;
        } else if (line.includes('edges OUT OF')) {
            section = 'outgoing';
            continue;
        }

        // Parse edge lines like: "PgIntegrationApp::process --[calls]--> PgIntegrationApp::make"
        const edgeMatch = line.match(/(.+?)\s+--\[(.+?)\]-->\s+(.+)/);
        if (edgeMatch && section) {
            const [, from, relation, to] = edgeMatch;

            if (section === 'incoming' && from && relation) {
                incoming.push({ from: from.trim(), relation: relation.trim() });
            } else if (section === 'outgoing' && to && relation) {
                outgoing.push({ to: to.trim(), relation: relation.trim() });
            }
        }
    }

    return { incoming, outgoing };
}

function wrapError(error: any, functionName: string): Error {
    if (error instanceof Error) {
        return new Error(`Error in ${functionName}: ${error.message}`);
    }
    return new Error(`Unknown error in ${functionName}: ${String(error)}`);
}

export function getAllModules(graphPath: string): string[] {
    const root = graphPath.split('/').slice(0, 2).join('/');
    const G = loadGraph(graphPath);
    if (!G) {
        console.error(`Error: Graph not found at ${graphPath}`);
        return [];
    }

    const res = new Set<string>();
    for (const node of G.nodes()) {
        const nodeData = G.node.get(node);
        if (nodeData && 'file_path' in nodeData && nodeData['file_path'].includes(root)) {
            res.add(node.split('::').slice(0, -1).join('::'));
        } else if (nodeData && 'location' in nodeData) {
            res.add(node.split('::').slice(0, -1).join('::'));
        }
    }
    return Array.from(res);
}

export function getModuleInfo(fdepFolder: string, moduleName: string): ModuleInfo[] {
    if (!fs.existsSync(fdepFolder) || !fs.lstatSync(fdepFolder).isDirectory()) {
        console.error(`Error: Folder doesn't exist: ${fdepFolder}`);
        return [];
    }

    const jsonFiles: string[] = [];
    const walk = (dir: string) => {
        const files = fs.readdirSync(dir);
        for (const file of files) {
            const filePath = path.join(dir, file);
            const stat = fs.statSync(filePath);
            if (stat.isDirectory()) {
                walk(filePath);
            } else if (file.endsWith('.json')) {
                jsonFiles.push(filePath);
            }
        }
    };
    walk(fdepFolder);

    const exactMatches: ModuleInfo[] = [];
    for (const filePath of jsonFiles) {
        try {
            const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
            if (Array.isArray(data)) {
                for (const item of data) {
                    if (typeof item === 'object' && item !== null && item.module === moduleName && 'name' in item) {
                        exactMatches.push(item);
                    }
                }
            }
        } catch (e) {
            if (e instanceof SyntaxError || e instanceof Error) {
                console.warn(`Warning: Could not read or parse ${filePath}: ${e.message}`);
            }
            continue;
        }
    }

    if (exactMatches.length > 0) {
        const uniqueMatches: ModuleInfo[] = [];
        const seen = new Set<string>();
        for (const match of exactMatches) {
            const representation = JSON.stringify(match, Object.keys(match).sort());
            if (!seen.has(representation)) {
                seen.add(representation);
                uniqueMatches.push(match);
            }
        }
        return uniqueMatches.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
    }

    const lazyMatches: ModuleInfo[] = [];
    for (const filePath of jsonFiles) {
        try {
            const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
            if (Array.isArray(data)) {
                for (const item of data) {
                    if (typeof item === 'object' && item !== null && (item.module || '').includes(moduleName) && 'name' in item) {
                        lazyMatches.push(item);
                    }
                }
            }
        } catch (e) {
            continue;
        }
    }

    if (lazyMatches.length > 0) {
        const uniqueMatches: ModuleInfo[] = [];
        const seen = new Set<string>();
        for (const match of lazyMatches) {
            const representation = JSON.stringify(match, Object.keys(match).sort());
            if (!seen.has(representation)) {
                seen.add(representation);
                uniqueMatches.push(match);
            }
        }
        return uniqueMatches.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
    }

    return [];
}

export function getFunctionInfo(fdepFolder: string, moduleName: string, componentName: string): ModuleInfo[] {
    if (!fs.existsSync(fdepFolder)) {
        console.error(`Error: Folder doesn't exist: ${fdepFolder}`);
        return [];
    }

    const components = getModuleInfo(fdepFolder, moduleName);
    for (const comp of components) {
        if (comp.name === componentName) {
            return [comp];
        }
    }

    console.error(`Error: '${componentName}' not found in module '${moduleName}'`);
    return [];
}

export function getFunctionChildren(graphPath: string, moduleName: string, componentName: string, depth: number = 1): any[][] {
    const G = loadGraph(graphPath);
    if (!G) {
        console.error(`Error: Graph not found at ${graphPath}`);
        return [];
    }

    const target = `${moduleName}::${componentName}`;
    if (!G.hasNode(target)) {
        console.error(`Error: Target '${target}' not in graph`);
        return [];
    }

    const result: any[][] = [];
    const visited = new Set<string>();
    const queue: [string, number][] = [[target, 0]];
    visited.add(target);

    while (queue.length > 0) {
        const [currentNode, currentDepth] = queue.shift()!;
        if (currentDepth >= depth) {
            continue;
        }

        for (const child of G.successors(currentNode)) {
            if (!visited.has(child)) {
                visited.add(child);
                const childDepth = currentDepth + 1;
                const [childModule, childComponent] = child.includes('::') ? child.split('::', 2) : ['', child];
                result.push([child, childModule, childComponent, childDepth]);
                if (childDepth < depth) {
                    queue.push([child, childDepth]);
                }
            }
        }
    }
    return result;
}

export function getFunctionParent(graphPath: string, moduleName: string, componentName: string, depth: number = 1): any[][] {
    const G = loadGraph(graphPath);
    if (!G) {
        console.error(`Error: Graph not found at ${graphPath}`);
        return [];
    }

    const target = `${moduleName}::${componentName}`;
    if (!G.hasNode(target)) {
        console.error(`Error: Target '${target}' not in graph`);
        return [];
    }

    const result: any[][] = [];
    const visited = new Set<string>();
    const queue: [string, number][] = [[target, 0]];
    visited.add(target);

    while (queue.length > 0) {
        const [currentNode, currentDepth] = queue.shift()!;
        if (currentDepth >= depth) {
            continue;
        }

        for (const parent of G.predecessors(currentNode)) {
            if (!visited.has(parent)) {
                visited.add(parent);
                const parentDepth = currentDepth + 1;
                const [parentModule, parentComponent] = parent.includes('::') ? parent.split('::', 2) : ['', parent];
                result.push([parent, parentModule, parentComponent, parentDepth]);
                if (parentDepth < depth) {
                    queue.push([parent, parentDepth]);
                }
            }
        }
    }
    return result;
}

export function getSubgraph(
    graphPath: string,
    moduleName: string,
    componentName: string,
    parentDepth: number = 1,
    childDepth: number = 1
): { nodes: any[][]; edges: any[][] } {
    const G = loadGraph(graphPath);
    if (!G) {
        console.error(`Error: Graph not found at ${graphPath}`);
        return { nodes: [], edges: [] };
    }
    const target = `${moduleName}::${componentName}`;
    if (!G.hasNode(target)) {
        console.error(`Error: Target '${target}' not in graph`);
        return { nodes: [], edges: [] };
    }

    const nodesToInclude = new Set<string>([target]);
    const parents = getFunctionParent(graphPath, moduleName, componentName, parentDepth);
    for (const parent of parents) {
        nodesToInclude.add(parent[0]);
    }
    const children = getFunctionChildren(graphPath, moduleName, componentName, childDepth);
    for (const child of children) {
        nodesToInclude.add(child[0]);
    }

    const subgraph = G.subgraph(Array.from(nodesToInclude));
    const nodes = subgraph.nodes().map((n: string) => {
        const [nodeModule, nodeComponent] = n.includes('::') ? n.split('::', 2) : ['', n];
        return [n, nodeModule, nodeComponent];
    });
    const edges = subgraph.edges();

    return { nodes, edges };
}

export function getCommonParents(graphPath: string, moduleName1: string, componentName1: string, moduleName2: string, componentName2: string): any[][] {
    const parents1 = getFunctionParent(graphPath, moduleName1, componentName1, Infinity);
    const parents2 = getFunctionParent(graphPath, moduleName2, componentName2, Infinity);

    const parents1Set = new Set(parents1.map(p => p[0]));
    const parents2Set = new Set(parents2.map(p => p[0]));

    const commonParentIds = new Set([...parents1Set].filter(p => parents2Set.has(p)));

    const parents1Dict = new Map(parents1.map(p => [p[0], p]));
    const parents2Dict = new Map(parents2.map(p => [p[0], p]));

    const commonParents: any[][] = [];
    for (const parentId of commonParentIds) {
        const parent1Info = parents1Dict.get(parentId)!;
        const parent2Info = parents2Dict.get(parentId)!;
        commonParents.push([
            parentId,
            parent1Info[1],
            parent1Info[2],
            parent1Info[3],
            parent2Info[3],
        ]);
    }

    commonParents.sort((a, b) => (a[3] + a[4]) - (b[3] + b[4]));
    return commonParents;
}

export function getCommonChildren(graphPath: string, moduleName1: string, componentName1: string, moduleName2: string, componentName2: string): any[][] {
    const children1 = getFunctionChildren(graphPath, moduleName1, componentName1, Infinity);
    const children2 = getFunctionChildren(graphPath, moduleName2, componentName2, Infinity);

    const children1Set = new Set(children1.map(c => c[0]));
    const children2Set = new Set(children2.map(c => c[0]));

    const commonChildIds = new Set([...children1Set].filter(c => children2Set.has(c)));

    const children1Dict = new Map(children1.map(c => [c[0], c]));
    const children2Dict = new Map(children2.map(c => [c[0], c]));

    const commonChildren: any[][] = [];
    for (const childId of commonChildIds) {
        const child1Info = children1Dict.get(childId)!;
        const child2Info = children2Dict.get(childId)!;
        commonChildren.push([
            childId,
            child1Info[1],
            child1Info[2],
            child1Info[3],
            child2Info[3],
        ]);
    }

    commonChildren.sort((a, b) => (a[3] + a[4]) - (b[3] + b[4]));
    return commonChildren;
}

export function getImportantNodes(fdepPath: string, outputDir: string = '', epsilon: number = 0.2, percentage: number = 5): string {
    const outputDirPath = path.resolve(outputDir);
    fs.mkdirSync(outputDirPath, { recursive: true });

    if (!fs.existsSync(fdepPath)) {
        throw new Error(`The specified fdep path does not exist: ${fdepPath}`);
    }
    if (epsilon > 1 || epsilon < 0) {
        epsilon = 0.2;
    }
    if (percentage > 20 || percentage <= 0) {
        percentage = 5;
    }

    const fdepNx = buildCleanGraph(fdepPath, false, outputDirPath);

    const count = fdepNx.numberOfNodes();
    const numSelections = Math.floor(count * percentage / 100);
    const heavyNodesByMetric = computeNodeMetrics({
        graph: fdepNx,
        epsilon: epsilon,
        numSelections: numSelections,
    });

    fs.writeFileSync(path.join(outputDirPath, 'ImportantNodes.json'), JSON.stringify(heavyNodesByMetric));
    return JSON.stringify({ status: 'ok' });
}

export async function findPath(
    graphPath: string,
    fromComponent: string,
    toComponent: string
): Promise<PathResult> {
    try {
        const G = loadGraph(graphPath);
        if (!G) {
            throw new Error(`Graph not found at ${graphPath}`);
        }

        if (!G.hasNode(fromComponent)) {
            throw new Error(`Source component '${fromComponent}' not in graph.`);
        }
        if (!G.hasNode(toComponent)) {
            throw new Error(`Target component '${toComponent}' not in graph.`);
        }

        try {
            const path = findFromSingleSource(G, fromComponent, toComponent);
            const formattedPath = path.join(' -> ');
            return parsePathResult(formattedPath);
        } catch (e: any) {
            if (e.name === 'NetworkXNoPath') {
                return { found: false, path: [], message: `No path found from '${fromComponent}' to '${toComponent}'.` };
            }
            throw e;
        }
    } catch (error) {
        throw wrapError(error, 'findPath');
    }
}

export async function getNeighbors(graphPath: string, component: string): Promise<NeighborResult> {
    try {
        const G = loadGraph(graphPath);
        if (!G) {
            throw new Error(`Graph not found at ${graphPath}`);
        }

        if (!G.hasNode(component)) {
            throw new Error(`Component '${component}' not in graph.`);
        }

        // To mimic the stdout for parseNeighborResult, we need to construct a string
        // that includes incoming and outgoing edges.
        let stdout = '';
        const preds = Array.from(G.predecessors(component));
        if (preds.length > 0) {
            stdout += `\nNodes with edges INTO '${component}' (${preds.length}):\n`;
            for (const p of preds) {
                const rel = G.getEdgeData(p, component) ? (G.getEdgeData(p, component) as any).relation || "" : "";
                stdout += `  ${p} --[${rel}]--> ${component}\n`;
            }
        } else {
            stdout += `\nNo incoming edges to '${component}'.\n`;
        }

        const succs = Array.from(G.successors(component));
        if (succs.length > 0) {
            stdout += `\nNodes with edges OUT OF '${component}' (${succs.length}):\n`;
            for (const s of succs) {
                const rel = G.getEdgeData(component, s) ? (G.getEdgeData(component, s) as any).relation || "" : "";
                stdout += `  ${component} --[${rel}]--> ${s}\n`;
            }
        } else {
            stdout += `\nNo outgoing edges from '${component}'.\n`;
        }

        return parseNeighborResult(stdout);
    } catch (error) {
        throw wrapError(error, 'getNeighbors');
    }
}

// (async () => {
//     // console.log(await findPath("/Users/jignyas.s/.xyne/dd1766ce5a6ff3ecca16060e112db785/graph/repo_function_calls.json", "Main::processSpecFolders'", "Main::isGenAll"));
//     console.log(await getSubgraph("/Users/jignyas.s/.xyne/dd1766ce5a6ff3ecca16060e112db785/graph/repo_function_calls.json", "Main", "processSpecFolders"));
// })();
