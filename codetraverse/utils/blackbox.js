"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
var __spreadArray = (this && this.__spreadArray) || function (to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
        if (ar || !(i in from)) {
            if (!ar) ar = Array.prototype.slice.call(from, 0, i);
            ar[i] = from[i];
        }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.getAllModules = getAllModules;
exports.getModuleInfo = getModuleInfo;
exports.getFunctionInfo = getFunctionInfo;
exports.getFunctionChildren = getFunctionChildren;
exports.getFunctionParent = getFunctionParent;
exports.getSubgraph = getSubgraph;
exports.getCommonParents = getCommonParents;
exports.getCommonChildren = getCommonChildren;
exports.getImportantNodes = getImportantNodes;
var fs = require("fs");
var path = require("path");
var path_1 = require("@/path");
var jsnetworkx_graph_1 = require("@/utils/jsnetworkx_graph");
var graph_partitioner_1 = require("@/utils/graph_partitioner");
var main_1 = require("@/main");
var argparse_1 = require("argparse");
function getAllModules(graphPath) {
    var root = graphPath.split('/').slice(0, 2).join('/');
    var G = (0, path_1.loadGraph)(graphPath);
    if (!G) {
        console.error("Error: Graph not found at ".concat(graphPath));
        return [];
    }
    var res = new Set();
    for (var _i = 0, _a = G.nodes(); _i < _a.length; _i++) {
        var node = _a[_i];
        var nodeData = G.node.get(node);
        if (nodeData && 'file_path' in nodeData && nodeData['file_path'].includes(root)) {
            res.add(node.split('::').slice(0, -1).join('::'));
        }
        else if (nodeData && 'location' in nodeData) {
            res.add(node.split('::').slice(0, -1).join('::'));
        }
    }
    return Array.from(res);
}
function getModuleInfo(fdepFolder, moduleName) {
    if (!fs.existsSync(fdepFolder) || !fs.lstatSync(fdepFolder).isDirectory()) {
        console.error("Error: Folder doesn't exist: ".concat(fdepFolder));
        return [];
    }
    var jsonFiles = [];
    var walk = function (dir) {
        var files = fs.readdirSync(dir);
        for (var _i = 0, files_1 = files; _i < files_1.length; _i++) {
            var file = files_1[_i];
            var filePath = path.join(dir, file);
            var stat = fs.statSync(filePath);
            if (stat.isDirectory()) {
                walk(filePath);
            }
            else if (file.endsWith('.json')) {
                jsonFiles.push(filePath);
            }
        }
    };
    walk(fdepFolder);
    var exactMatches = [];
    for (var _i = 0, jsonFiles_1 = jsonFiles; _i < jsonFiles_1.length; _i++) {
        var filePath = jsonFiles_1[_i];
        try {
            var data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
            if (Array.isArray(data)) {
                for (var _a = 0, data_1 = data; _a < data_1.length; _a++) {
                    var item = data_1[_a];
                    if (typeof item === 'object' && item !== null && item.module === moduleName && 'name' in item) {
                        exactMatches.push(item);
                    }
                }
            }
        }
        catch (e) {
            if (e instanceof SyntaxError || e instanceof Error) {
                console.warn("Warning: Could not read or parse ".concat(filePath, ": ").concat(e.message));
            }
            continue;
        }
    }
    if (exactMatches.length > 0) {
        var uniqueMatches = [];
        var seen = new Set();
        for (var _b = 0, exactMatches_1 = exactMatches; _b < exactMatches_1.length; _b++) {
            var match = exactMatches_1[_b];
            var representation = JSON.stringify(match, Object.keys(match).sort());
            if (!seen.has(representation)) {
                seen.add(representation);
                uniqueMatches.push(match);
            }
        }
        return uniqueMatches.sort(function (a, b) { return (a.name || '').localeCompare(b.name || ''); });
    }
    var lazyMatches = [];
    for (var _c = 0, jsonFiles_2 = jsonFiles; _c < jsonFiles_2.length; _c++) {
        var filePath = jsonFiles_2[_c];
        try {
            var data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
            if (Array.isArray(data)) {
                for (var _d = 0, data_2 = data; _d < data_2.length; _d++) {
                    var item = data_2[_d];
                    if (typeof item === 'object' && item !== null && (item.module || '').includes(moduleName) && 'name' in item) {
                        lazyMatches.push(item);
                    }
                }
            }
        }
        catch (e) {
            continue;
        }
    }
    if (lazyMatches.length > 0) {
        var uniqueMatches = [];
        var seen = new Set();
        for (var _e = 0, lazyMatches_1 = lazyMatches; _e < lazyMatches_1.length; _e++) {
            var match = lazyMatches_1[_e];
            var representation = JSON.stringify(match, Object.keys(match).sort());
            if (!seen.has(representation)) {
                seen.add(representation);
                uniqueMatches.push(match);
            }
        }
        return uniqueMatches.sort(function (a, b) { return (a.name || '').localeCompare(b.name || ''); });
    }
    return [];
}
function getFunctionInfo(fdepFolder, moduleName, componentName) {
    if (!fs.existsSync(fdepFolder)) {
        console.error("Error: Folder doesn't exist: ".concat(fdepFolder));
        return [];
    }
    var components = getModuleInfo(fdepFolder, moduleName);
    for (var _i = 0, components_1 = components; _i < components_1.length; _i++) {
        var comp = components_1[_i];
        if (comp.name === componentName) {
            return [comp];
        }
    }
    console.error("Error: '".concat(componentName, "' not found in module '").concat(moduleName, "'"));
    return [];
}
function getFunctionChildren(graphPath, moduleName, componentName, depth) {
    if (depth === void 0) { depth = 1; }
    var G = (0, path_1.loadGraph)(graphPath);
    if (!G) {
        console.error("Error: Graph not found at ".concat(graphPath));
        return [];
    }
    var target = "".concat(moduleName, "::").concat(componentName);
    if (!G.hasNode(target)) {
        console.error("Error: Target '".concat(target, "' not in graph"));
        return [];
    }
    var result = [];
    var visited = new Set();
    var queue = [[target, 0]];
    visited.add(target);
    while (queue.length > 0) {
        var _a = queue.shift(), currentNode = _a[0], currentDepth = _a[1];
        if (currentDepth >= depth) {
            continue;
        }
        for (var _i = 0, _b = G.successors(currentNode); _i < _b.length; _i++) {
            var child = _b[_i];
            if (!visited.has(child)) {
                visited.add(child);
                var childDepth = currentDepth + 1;
                var _c = child.includes('::') ? child.split('::', 2) : ['', child], childModule = _c[0], childComponent = _c[1];
                result.push([child, childModule, childComponent, childDepth]);
                if (childDepth < depth) {
                    queue.push([child, childDepth]);
                }
            }
        }
    }
    return result;
}
function getFunctionParent(graphPath, moduleName, componentName, depth) {
    if (depth === void 0) { depth = 1; }
    var G = (0, path_1.loadGraph)(graphPath);
    if (!G) {
        console.error("Error: Graph not found at ".concat(graphPath));
        return [];
    }
    var target = "".concat(moduleName, "::").concat(componentName);
    if (!G.hasNode(target)) {
        console.error("Error: Target '".concat(target, "' not in graph"));
        return [];
    }
    var result = [];
    var visited = new Set();
    var queue = [[target, 0]];
    visited.add(target);
    while (queue.length > 0) {
        var _a = queue.shift(), currentNode = _a[0], currentDepth = _a[1];
        if (currentDepth >= depth) {
            continue;
        }
        for (var _i = 0, _b = G.predecessors(currentNode); _i < _b.length; _i++) {
            var parent_1 = _b[_i];
            if (!visited.has(parent_1)) {
                visited.add(parent_1);
                var parentDepth = currentDepth + 1;
                var _c = parent_1.includes('::') ? parent_1.split('::', 2) : ['', parent_1], parentModule = _c[0], parentComponent = _c[1];
                result.push([parent_1, parentModule, parentComponent, parentDepth]);
                if (parentDepth < depth) {
                    queue.push([parent_1, parentDepth]);
                }
            }
        }
    }
    return result;
}
function getSubgraph(graphPath, moduleName, componentName, parentDepth, childDepth) {
    if (parentDepth === void 0) { parentDepth = 1; }
    if (childDepth === void 0) { childDepth = 1; }
    var G = (0, path_1.loadGraph)(graphPath);
    if (!G) {
        return null;
    }
    var target = "".concat(moduleName, "::").concat(componentName);
    if (!G.hasNode(target)) {
        return null;
    }
    var nodesToInclude = new Set([target]);
    var parents = getFunctionParent(graphPath, moduleName, componentName, parentDepth);
    for (var _i = 0, parents_1 = parents; _i < parents_1.length; _i++) {
        var parent_2 = parents_1[_i];
        nodesToInclude.add(parent_2[0]);
    }
    var children = getFunctionChildren(graphPath, moduleName, componentName, childDepth);
    for (var _a = 0, children_1 = children; _a < children_1.length; _a++) {
        var child = children_1[_a];
        nodesToInclude.add(child[0]);
    }
    return G.subgraph(Array.from(nodesToInclude));
}
function getCommonParents(graphPath, moduleName1, componentName1, moduleName2, componentName2) {
    var parents1 = getFunctionParent(graphPath, moduleName1, componentName1, Infinity);
    var parents2 = getFunctionParent(graphPath, moduleName2, componentName2, Infinity);
    var parents1Set = new Set(parents1.map(function (p) { return p[0]; }));
    var parents2Set = new Set(parents2.map(function (p) { return p[0]; }));
    var commonParentIds = new Set(__spreadArray([], parents1Set, true).filter(function (p) { return parents2Set.has(p); }));
    var parents1Dict = new Map(parents1.map(function (p) { return [p[0], p]; }));
    var parents2Dict = new Map(parents2.map(function (p) { return [p[0], p]; }));
    var commonParents = [];
    for (var _i = 0, commonParentIds_1 = commonParentIds; _i < commonParentIds_1.length; _i++) {
        var parentId = commonParentIds_1[_i];
        var parent1Info = parents1Dict.get(parentId);
        var parent2Info = parents2Dict.get(parentId);
        commonParents.push([
            parentId,
            parent1Info[1],
            parent1Info[2],
            parent1Info[3],
            parent2Info[3],
        ]);
    }
    commonParents.sort(function (a, b) { return (a[3] + a[4]) - (b[3] + b[4]); });
    return commonParents;
}
function getCommonChildren(graphPath, moduleName1, componentName1, moduleName2, componentName2) {
    var children1 = getFunctionChildren(graphPath, moduleName1, componentName1, Infinity);
    var children2 = getFunctionChildren(graphPath, moduleName2, componentName2, Infinity);
    var children1Set = new Set(children1.map(function (c) { return c[0]; }));
    var children2Set = new Set(children2.map(function (c) { return c[0]; }));
    var commonChildIds = new Set(__spreadArray([], children1Set, true).filter(function (c) { return children2Set.has(c); }));
    var children1Dict = new Map(children1.map(function (c) { return [c[0], c]; }));
    var children2Dict = new Map(children2.map(function (c) { return [c[0], c]; }));
    var commonChildren = [];
    for (var _i = 0, commonChildIds_1 = commonChildIds; _i < commonChildIds_1.length; _i++) {
        var childId = commonChildIds_1[_i];
        var child1Info = children1Dict.get(childId);
        var child2Info = children2Dict.get(childId);
        commonChildren.push([
            childId,
            child1Info[1],
            child1Info[2],
            child1Info[3],
            child2Info[3],
        ]);
    }
    commonChildren.sort(function (a, b) { return (a[3] + a[4]) - (b[3] + b[4]); });
    return commonChildren;
}
function getImportantNodes(fdepPath, outputDir, epsilon, percentage) {
    if (outputDir === void 0) { outputDir = ''; }
    if (epsilon === void 0) { epsilon = 0.2; }
    if (percentage === void 0) { percentage = 5; }
    var outputDirPath = path.resolve(outputDir);
    fs.mkdirSync(outputDirPath, { recursive: true });
    if (!fs.existsSync(fdepPath)) {
        throw new Error("The specified fdep path does not exist: ".concat(fdepPath));
    }
    if (epsilon > 1 || epsilon < 0) {
        epsilon = 0.2;
    }
    if (percentage > 20 || percentage <= 0) {
        percentage = 5;
    }
    var fdepNx = (0, jsnetworkx_graph_1.buildCleanGraph)(fdepPath, false, outputDirPath);
    var count = fdepNx.numberOfNodes();
    var numSelections = Math.floor(count * percentage / 100);
    var heavyNodesByMetric = (0, graph_partitioner_1.computeNodeMetrics)({
        graph: fdepNx,
        epsilon: epsilon,
        numSelections: numSelections,
    });
    fs.writeFileSync(path.join(outputDirPath, 'ImportantNodes.json'), JSON.stringify(heavyNodesByMetric));
    return JSON.stringify({ status: 'ok' });
}
function main() {
    return __awaiter(this, void 0, void 0, function () {
        var parser, subparsers, parserModule, parserFunc, parserChildren, parserParent, parserSubgraph, parserCommonParents, parserCommonChildren, parserCreateFdep, parserGetAllModules, parserGetImportantNodes, args, result, out;
        return __generator(this, function (_a) {
            parser = new argparse_1.ArgumentParser({
                description: 'Code Analysis Tool',
            });
            subparsers = parser.add_subparsers({ dest: 'function', help: 'Available functions' });
            parserModule = subparsers.add_parser('getModuleInfo', { help: 'Get module information' });
            parserModule.add_argument('fdep_folder', { help: 'Path to fdep folder' });
            parserModule.add_argument('module_name', { help: 'Module name to search for' });
            parserFunc = subparsers.add_parser('getFunctionInfo', { help: 'Get function information' });
            parserFunc.add_argument('fdep_folder', { help: 'Path to fdep folder' });
            parserFunc.add_argument('module_name', { help: 'Module name' });
            parserFunc.add_argument('component_name', { help: 'Component name' });
            parserChildren = subparsers.add_parser('getFunctionChildren', { help: 'Get function children' });
            parserChildren.add_argument('graph_path', { help: 'Path to graph file' });
            parserChildren.add_argument('module_name', { help: 'Module name' });
            parserChildren.add_argument('component_name', { help: 'Component name' });
            parserChildren.add_argument('--depth', { type: 'int', default: 1, help: 'Search depth (default: 1)' });
            parserParent = subparsers.add_parser('getFunctionParent', { help: 'Get function parents' });
            parserParent.add_argument('graph_path', { help: 'Path to graph file' });
            parserParent.add_argument('module_name', { help: 'Module name' });
            parserParent.add_argument('component_name', { help: 'Component name' });
            parserParent.add_argument('--depth', { type: 'int', default: 1, help: 'Search depth (default: 1)' });
            parserSubgraph = subparsers.add_parser('getSubgraph', { help: 'Get subgraph' });
            parserSubgraph.add_argument('graph_path', { help: 'Path to graph file' });
            parserSubgraph.add_argument('module_name', { help: 'Module name' });
            parserSubgraph.add_argument('component_name', { help: 'Component name' });
            parserSubgraph.add_argument('--parent_depth', { type: 'int', default: 1, help: 'Parent depth (default: 1)' });
            parserSubgraph.add_argument('--child_depth', { type: 'int', default: 1, help: 'Child depth (default: 1)' });
            parserCommonParents = subparsers.add_parser('getCommonParents', { help: 'Get common parents' });
            parserCommonParents.add_argument('graph_path', { help: 'Path to graph file' });
            parserCommonParents.add_argument('module_name1', { help: 'First module name' });
            parserCommonParents.add_argument('component_name1', { help: 'First component name' });
            parserCommonParents.add_argument('module_name2', { help: 'Second module name' });
            parserCommonParents.add_argument('component_name2', { help: 'Second component name' });
            parserCommonChildren = subparsers.add_parser('getCommonChildren', { help: 'Get common children' });
            parserCommonChildren.add_argument('graph_path', { help: 'Path to graph file' });
            parserCommonChildren.add_argument('module_name1', { help: 'First module name' });
            parserCommonChildren.add_argument('component_name1', { help: 'First component name' });
            parserCommonChildren.add_argument('module_name2', { help: 'Second module name' });
            parserCommonChildren.add_argument('component_name2', { help: 'Second component name' });
            parserCreateFdep = subparsers.add_parser('createFdepData', { help: 'Create Fdep Data' });
            parserCreateFdep.add_argument('root_dir', { help: 'The directory for which fdep should be created' });
            parserCreateFdep.add_argument('--output_base', { help: 'Path for fdep output', default: './output/fdep' });
            parserCreateFdep.add_argument('--graph_dir', { help: 'path for graph output', default: './output/graph' });
            parserCreateFdep.add_argument('--clear_existing', { help: 'Clear existing output', default: true });
            parserGetAllModules = subparsers.add_parser('getAllModules', { help: 'Get all valid modules in a graph' });
            parserGetAllModules.add_argument('graph_path', { help: 'Location to the graphml file' });
            parserGetImportantNodes = subparsers.add_parser('getImportantNodes', { help: 'Get important nodes' });
            parserGetImportantNodes.add_argument('fdep_path', { help: 'The file path to fdep' });
            parserGetImportantNodes.add_argument('--output_path', { type: 'str', default: '', help: 'The file path to save the network graph' });
            parserGetImportantNodes.add_argument('--epsilon', { type: 'float', default: 0.2, help: 'Epsilon for epsilon-greedy algorithm' });
            parserGetImportantNodes.add_argument('--percentage', { type: 'int', default: 5, help: 'Percentage of codebase for important nodes' });
            args = parser.parse_args();
            try {
                result = void 0;
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
                        out = result ? { nodes: result.nodes(), edges: result.edges() } : { nodes: [], edges: [] };
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
                        (0, main_1.createFdepData)(args.root_dir, args.output_base, args.graph_dir, args.clear_existing);
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
            }
            catch (e) {
                if (e instanceof Error) {
                    console.error("Error: ".concat(e.message));
                }
                process.exit(1);
            }
            return [2 /*return*/];
        });
    });
}
if (require.main === module) {
    main();
}
