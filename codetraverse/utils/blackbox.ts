import 'module-alias/register';
import * as fs from 'fs';
import * as path from 'path';
import { loadGraph } from '@/path';
import { buildCleanGraph } from '@/utils/jsnetworkx_graph';
import { computeNodeMetrics } from '@/utils/graph_partitioner';
import { createFdepData } from '@/main';
import { ArgumentParser } from 'argparse';
import * as jsnx from 'jsnetworkx';

type ModuleInfo = { [key: string]: any };

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

export function getSubgraph(graphPath: string, moduleName: string, componentName: string, parentDepth: number = 1, childDepth: number = 1): jsnx.Graph | null {
    const G = loadGraph(graphPath);
    if (!G) {
        return null;
    }
    const target = `${moduleName}::${componentName}`;
    if (!G.hasNode(target)) {
        return null;
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

    return G.subgraph(Array.from(nodesToInclude));
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

async function main() {
    const parser = new ArgumentParser({
        description: 'Code Analysis Tool',
    });
    const subparsers = parser.add_subparsers({ dest: 'function', help: 'Available functions' });

    const parserModule = subparsers.add_parser('getModuleInfo', { help: 'Get module information' });
    parserModule.add_argument('fdep_folder', { help: 'Path to fdep folder' });
    parserModule.add_argument('module_name', { help: 'Module name to search for' });

    const parserFunc = subparsers.add_parser('getFunctionInfo', { help: 'Get function information' });
    parserFunc.add_argument('fdep_folder', { help: 'Path to fdep folder' });
    parserFunc.add_argument('module_name', { help: 'Module name' });
    parserFunc.add_argument('component_name', { help: 'Component name' });

    const parserChildren = subparsers.add_parser('getFunctionChildren', { help: 'Get function children' });
    parserChildren.add_argument('graph_path', { help: 'Path to graph file' });
    parserChildren.add_argument('module_name', { help: 'Module name' });
    parserChildren.add_argument('component_name', { help: 'Component name' });
    parserChildren.add_argument('--depth', { type: 'int', default: 1, help: 'Search depth (default: 1)' });

    const parserParent = subparsers.add_parser('getFunctionParent', { help: 'Get function parents' });
    parserParent.add_argument('graph_path', { help: 'Path to graph file' });
    parserParent.add_argument('module_name', { help: 'Module name' });
    parserParent.add_argument('component_name', { help: 'Component name' });
    parserParent.add_argument('--depth', { type: 'int', default: 1, help: 'Search depth (default: 1)' });

    const parserSubgraph = subparsers.add_parser('getSubgraph', { help: 'Get subgraph' });
    parserSubgraph.add_argument('graph_path', { help: 'Path to graph file' });
    parserSubgraph.add_argument('module_name', { help: 'Module name' });
    parserSubgraph.add_argument('component_name', { help: 'Component name' });
    parserSubgraph.add_argument('--parent_depth', { type: 'int', default: 1, help: 'Parent depth (default: 1)' });
    parserSubgraph.add_argument('--child_depth', { type: 'int', default: 1, help: 'Child depth (default: 1)' });

    const parserCommonParents = subparsers.add_parser('getCommonParents', { help: 'Get common parents' });
    parserCommonParents.add_argument('graph_path', { help: 'Path to graph file' });
    parserCommonParents.add_argument('module_name1', { help: 'First module name' });
    parserCommonParents.add_argument('component_name1', { help: 'First component name' });
    parserCommonParents.add_argument('module_name2', { help: 'Second module name' });
    parserCommonParents.add_argument('component_name2', { help: 'Second component name' });

    const parserCommonChildren = subparsers.add_parser('getCommonChildren', { help: 'Get common children' });
    parserCommonChildren.add_argument('graph_path', { help: 'Path to graph file' });
    parserCommonChildren.add_argument('module_name1', { help: 'First module name' });
    parserCommonChildren.add_argument('component_name1', { help: 'First component name' });
    parserCommonChildren.add_argument('module_name2', { help: 'Second module name' });
    parserCommonChildren.add_argument('component_name2', { help: 'Second component name' });

    const parserCreateFdep = subparsers.add_parser('createFdepData', { help: 'Create Fdep Data' });
    parserCreateFdep.add_argument('root_dir', { help: 'The directory for which fdep should be created' });
    parserCreateFdep.add_argument('--output_base', { help: 'Path for fdep output', default: './output/fdep' });
    parserCreateFdep.add_argument('--graph_dir', { help: 'path for graph output', default: './output/graph' });
    parserCreateFdep.add_argument('--clear_existing', { help: 'Clear existing output', default: true });

    const parserGetAllModules = subparsers.add_parser('getAllModules', { help: 'Get all valid modules in a graph' });
    parserGetAllModules.add_argument('graph_path', { help: 'Location to the graphml file' });

    const parserGetImportantNodes = subparsers.add_parser('getImportantNodes', { help: 'Get important nodes' });
    parserGetImportantNodes.add_argument('fdep_path', { help: 'The file path to fdep' });
    parserGetImportantNodes.add_argument('--output_path', { type: 'str', default: '', help: 'The file path to save the network graph' });
    parserGetImportantNodes.add_argument('--epsilon', { type: 'float', default: 0.2, help: 'Epsilon for epsilon-greedy algorithm' });
    parserGetImportantNodes.add_argument('--percentage', { type: 'int', default: 5, help: 'Percentage of codebase for important nodes' });

    const args = parser.parse_args();

    try {
        let result: any;
        switch (args.function) {
            case 'getModuleInfo':
                result = getModuleInfo(args.fdep_folder, args.module_name);
                console.log(JSON.stringify(result, null, 2));
                break;
            case 'getFunctionInfo':
                result = getFunctionInfo(args.fdep_folder, args.module_name, args.component_name);
                console.log(JSON.stringify(result, null, 2));
                break;
            case 'getFunctionChildren':
                result = getFunctionChildren(args.graph_path, args.module_name, args.component_name, args.depth);
                console.log(JSON.stringify(result, null, 2));
                break;
            case 'getFunctionParent':
                result = getFunctionParent(args.graph_path, args.module_name, args.component_name, args.depth);
                console.log(JSON.stringify(result, null, 2));
                break;
            case 'getSubgraph':
                result = getSubgraph(args.graph_path, args.module_name, args.component_name, args.parent_depth, args.child_depth);
                const out = result ? { nodes: result.nodes(), edges: result.edges() } : { nodes: [], edges: [] };
                console.log(JSON.stringify(out));
                break;
            case 'getCommonParents':
                result = getCommonParents(args.graph_path, args.module_name1, args.component_name1, args.module_name2, args.component_name2);
                console.log(JSON.stringify(result, null, 2));
                break;
            case 'getCommonChildren':
                result = getCommonChildren(args.graph_path, args.module_name1, args.component_name1, args.module_name2, args.component_name2);
                console.log(JSON.stringify(result, null, 2));
                break;
            case 'getImportantNodes':
                result = getImportantNodes(args.fdep_path, args.output_path, args.epsilon, args.percentage);
                console.log(JSON.stringify(result, null, 2));
                break;
            case 'createFdepData':
                createFdepData(args.root_dir, args.output_base, args.graph_dir, args.clear_existing);
                console.log(JSON.stringify({ status: 'success' }, null, 2));
                break;
            case 'getAllModules':
                result = getAllModules(args.graph_path);
                console.log(JSON.stringify(result, null, 2));
                break;
            default:
                parser.print_help();
                break;
        }
    } catch (e) {
        if (e instanceof Error) {
            console.error(`Error: ${e.message}`);
        }
        process.exit(1);
    }
}

if (require.main === module) {
    main();
}
