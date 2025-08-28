"use strict";
var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
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
exports.buildGraphFromSchema = buildGraphFromSchema;
exports.buildCleanGraph = buildCleanGraph;
var fs = require("fs");
var path = require("path");
var jsnx = require("jsnetworkx");
function loadComponents(fdepDir) {
    var funcs = {};
    for (var _i = 0, _a = fs.readdirSync(fdepDir); _i < _a.length; _i++) {
        var dirpath = _a[_i];
        var fullpath = path.join(fdepDir, dirpath);
        if (fs.statSync(fullpath).isDirectory()) {
            for (var _b = 0, _c = fs.readdirSync(fullpath); _b < _c.length; _b++) {
                var fn = _c[_b];
                if (!fn.endsWith(".json")) {
                    continue;
                }
                var subpath = path.join(fullpath, fn);
                var data = JSON.parse(fs.readFileSync(subpath, "utf-8"));
                for (var _d = 0, data_1 = data; _d < data_1.length; _d++) {
                    var comp = data_1[_d];
                    var fq = "".concat(comp.module, "::").concat(comp.name);
                    funcs[fq] = comp;
                }
            }
        }
    }
    return funcs;
}
function loadComponentsWithoutHash(fdepDir) {
    var components = [];
    for (var _i = 0, _a = fs.readdirSync(fdepDir); _i < _a.length; _i++) {
        var dirpath = _a[_i];
        var fullpath = path.join(fdepDir, dirpath);
        if (fs.statSync(fullpath).isDirectory()) {
            for (var _b = 0, _c = fs.readdirSync(fullpath); _b < _c.length; _b++) {
                var fn = _c[_b];
                if (!fn.endsWith(".json")) {
                    continue;
                }
                var subpath = path.join(fullpath, fn);
                var data = JSON.parse(fs.readFileSync(subpath, "utf-8"));
                components.push.apply(components, data);
            }
        }
    }
    return components;
}
function buildGraphFromSchema(schema) {
    var G = new jsnx.DiGraph();
    for (var _i = 0, _a = schema.nodes; _i < _a.length; _i++) {
        var node = _a[_i];
        var nid = node.id;
        var attrs = {};
        for (var k in node) {
            if (k === "id") {
                continue;
            }
            var v = node[k];
            if (v === null) {
                attrs[k] = "";
            }
            else if (typeof v === "string" ||
                typeof v === "number" ||
                typeof v === "boolean") {
                attrs[k] = v;
            }
            else {
                attrs[k] = JSON.stringify(v);
            }
        }
        G.addNode(nid, attrs);
    }
    for (var _b = 0, _c = schema.edges; _b < _c.length; _b++) {
        var edge = _c[_b];
        var src = edge.from;
        var dst = edge.to;
        var rel = edge.relation || "";
        G.addEdge(src, dst, { relation: rel });
    }
    return G;
}
function preprocessGraph(G) {
    var nodesToRemove = G.nodes(true).filter(function (_a) {
        var attrs = _a[1];
        return attrs.code === "";
    });
    for (var _i = 0, nodesToRemove_1 = nodesToRemove; _i < nodesToRemove_1.length; _i++) {
        var node = nodesToRemove_1[_i][0];
        G.removeNode(node);
    }
    return G;
}
function buildCleanGraph(folderPath, saveAsJson, outputPath) {
    if (saveAsJson === void 0) { saveAsJson = false; }
    if (outputPath === void 0) { outputPath = ""; }
    var jsonFolder = folderPath;
    var fdepNx = buildGraphFromFolder(jsonFolder, saveAsJson, outputPath);
    var fdepNxProcessed = preprocessGraph(fdepNx);
    return fdepNxProcessed;
}
function buildGraphFromFolder(folderPath, saveAsJson, outputPath) {
    if (saveAsJson === void 0) { saveAsJson = false; }
    if (outputPath === void 0) { outputPath = ""; }
    var G = new jsnx.DiGraph();
    for (var _i = 0, _a = fs.readdirSync(folderPath); _i < _a.length; _i++) {
        var root = _a[_i];
        var fullPath = path.join(folderPath, root);
        if (fs.statSync(fullPath).isDirectory()) {
            for (var _b = 0, _c = fs.readdirSync(fullPath); _b < _c.length; _b++) {
                var fname = _c[_b];
                if (!fname.endsWith(".json")) {
                    continue;
                }
                var subpath = path.join(fullPath, fname);
                try {
                    var data = JSON.parse(fs.readFileSync(subpath, "utf-8"));
                    processModule(data, G);
                }
                catch (e) {
                    console.error(e);
                    continue;
                }
            }
        }
    }
    if (saveAsJson) {
        graphToJson(G, outputPath);
    }
    return G;
}
function graphToJson(G, outputPath) {
    var nodes = G.nodes(true).map(function (_a) {
        var node = _a[0], attrs = _a[1];
        return (__assign({ id: node }, attrs));
    });
    var edges = G.edges(true).map(function (_a) {
        var u = _a[0], v = _a[1], attrs = _a[2];
        return (__assign({ from: u, to: v }, attrs));
    });
    var graphData = { nodes: nodes, edges: edges };
    fs.writeFileSync(path.join(outputPath, "fdep.json"), JSON.stringify(graphData, null, 2));
}
function addLineNum(node) {
    var resCode = [];
    var ogCode = node.code || "";
    var start = node.start_line || -1;
    var end = node.end_line || -1;
    if (start < 0 || end < 0) {
        return ogCode;
    }
    var lines = ogCode.split("\n");
    var maxLineNumLen = (lines.length + 1).toString().length;
    for (var i = 0; i < lines.length; i++) {
        var lineNum = (i + start).toString().padStart(maxLineNumLen, " ");
        var formattedLine = "".concat(lineNum, " | ").concat(lines[i]);
        resCode.push(formattedLine);
    }
    return resCode.join("\n");
}
function addOrUpdateNode(G, key, meta, mergeLists) {
    if (mergeLists === void 0) { mergeLists = true; }
    if (!G.hasNode(key)) {
        G.addNode(key, meta);
        return;
    }
    var existing = G.node.get(key);
    for (var k in meta) {
        var v = meta[k];
        if (mergeLists && Array.isArray(v) && Array.isArray(existing[k])) {
            existing[k] = __spreadArray([], new Set(__spreadArray(__spreadArray([], existing[k], true), v, true)), true);
        }
        else {
            existing[k] = v;
        }
    }
}
function processModule(moduleData, G) {
    for (var _i = 0, moduleData_1 = moduleData; _i < moduleData_1.length; _i++) {
        var node = moduleData_1[_i];
        if (typeof node !== "object" || node === null) {
            continue;
        }
        if (node.kind !== "function") {
            continue;
        }
        var nodeKey = "".concat(node.name || "_", "--").concat(node.module || "_");
        var children = new Set();
        for (var _a = 0, _b = node.function_calls || []; _a < _b.length; _a++) {
            var c = _b[_a];
            if (typeof c === "object" && c !== null && c.context === "function_call") {
                children.add("".concat(c.base || "_", "--").concat((c.modules && c.modules[0]) || "_"));
            }
        }
        var nodeMeta = {
            code: addLineNum(node),
            type_signature: node.type_signature || "",
            types_used: node.type_dependencies || [],
        };
        addOrUpdateNode(G, nodeKey, nodeMeta, false);
        for (var _c = 0, children_1 = children; _c < children_1.length; _c++) {
            var ck = children_1[_c];
            if (!G.hasNode(ck)) {
                G.addNode(ck);
            }
            G.addEdge(nodeKey, ck);
        }
    }
}
function topRootsByDescendants(G, topN) {
    if (topN === void 0) { topN = 10; }
    var roots = G.nodes().filter(function (n) { return G.inDegree(n) === 0; });
    var rootCounts = [];
    for (var _i = 0, roots_1 = roots; _i < roots_1.length; _i++) {
        var r = roots_1[_i];
        var count = jsnx.descendants(G, r).length;
        rootCounts.push([r, count]);
    }
    rootCounts.sort(function (a, b) { return a[1] - b[1]; });
    return rootCounts.slice(0, topN);
}
