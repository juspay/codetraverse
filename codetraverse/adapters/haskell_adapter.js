"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.adaptHaskellComponents = adaptHaskellComponents;
function adaptHaskellComponents(rawComponents) {
    var nodes = [];
    var edges = [];
    var nodeIds = new Set();
    var allCompsByModule = {};
    var mainModulesByFile = {};
    for (var _i = 0, rawComponents_1 = rawComponents; _i < rawComponents_1.length; _i++) {
        var comp = rawComponents_1[_i];
        if (comp.kind === "module_header") {
            mainModulesByFile[comp.filePath] = comp.name;
        }
    }
    for (var _a = 0, rawComponents_2 = rawComponents; _a < rawComponents_2.length; _a++) {
        var comp = rawComponents_2[_a];
        var name_1 = comp.name;
        var filePath = comp.filePath;
        if (!name_1 || !filePath)
            continue;
        var compModule = comp.module || mainModulesByFile[filePath];
        if (!compModule)
            continue;
        comp.module = compModule;
        if (!allCompsByModule[compModule]) {
            allCompsByModule[compModule] = [];
        }
        allCompsByModule[compModule].push(comp);
    }
    var compsByFile = {};
    for (var _b = 0, rawComponents_3 = rawComponents; _b < rawComponents_3.length; _b++) {
        var comp = rawComponents_3[_b];
        if (comp.filePath) {
            if (!compsByFile[comp.filePath]) {
                compsByFile[comp.filePath] = [];
            }
            compsByFile[comp.filePath].push(comp);
        }
    }
    for (var filePath in compsByFile) {
        var fileComps = compsByFile[filePath];
        var importAliasMap = {};
        for (var _c = 0, fileComps_1 = fileComps; _c < fileComps_1.length; _c++) {
            var imp = fileComps_1[_c];
            if (imp.kind === "import" && imp.alias) {
                importAliasMap[imp.alias] = imp.module;
            }
        }
        for (var _d = 0, fileComps_2 = fileComps; _d < fileComps_2.length; _d++) {
            var comp = fileComps_2[_d];
            var kind = comp.kind, name_2 = comp.name, compModule = comp.module;
            if (!kind || !name_2 || !compModule)
                continue;
            var sourceId = "".concat(compModule, "::").concat(name_2);
            if (!nodeIds.has(sourceId)) {
                var nodeCategory = kind;
                if (kind === "module_header")
                    nodeCategory = "module";
                if (kind === "class")
                    nodeCategory = "typeclass";
                nodes.push({
                    id: sourceId,
                    category: nodeCategory,
                    name: name_2,
                    file_path: comp.filePath || "",
                    location: { start: comp.startLine, end: comp.endLine },
                });
                nodeIds.add(sourceId);
            }
            if (kind === "module_header") {
                var _loop_1 = function (exportName) {
                    if (importAliasMap[exportName]) {
                        var alias_1 = exportName;
                        var actualModuleNames = fileComps
                            .filter(function (imp) { return imp.alias === alias_1; })
                            .map(function (imp) { return imp.module; });
                        for (var _p = 0, actualModuleNames_1 = actualModuleNames; _p < actualModuleNames_1.length; _p++) {
                            var actualModuleName = actualModuleNames_1[_p];
                            for (var _q = 0, _r = allCompsByModule[actualModuleName] ||
                                []; _q < _r.length; _q++) {
                                var targetComp = _r[_q];
                                var targetName = targetComp.name;
                                if (!targetName)
                                    continue;
                                var proxyId = "".concat(compModule, "::").concat(targetName);
                                if (!nodeIds.has(proxyId)) {
                                    nodes.push({
                                        id: proxyId,
                                        category: "reexport",
                                        name: targetName,
                                        file_path: comp.filePath || "",
                                        location: {},
                                    });
                                    nodeIds.add(proxyId);
                                }
                                edges.push({
                                    from: sourceId,
                                    to: proxyId,
                                    relation: "exports",
                                });
                                var actualId = "".concat(targetComp.module, "::").concat(targetName);
                                edges.push({
                                    from: proxyId,
                                    to: actualId,
                                    relation: "reexport_of",
                                });
                            }
                        }
                    }
                    else {
                        edges.push({
                            from: sourceId,
                            to: "".concat(compModule, "::").concat(exportName),
                            relation: "exports",
                        });
                    }
                };
                for (var _e = 0, _f = comp.exports || []; _e < _f.length; _e++) {
                    var exportName = _f[_e];
                    _loop_1(exportName);
                }
            }
            else if (kind === "function") {
                for (var _g = 0, _h = comp.functionCalls || []; _g < _h.length; _g++) {
                    var call = _h[_g];
                    var callBase = call.base || call.name;
                    if (!callBase)
                        continue;
                    var targetModule = (call.modules && call.modules[0]) || compModule;
                    edges.push({
                        from: sourceId,
                        to: "".concat(targetModule, "::").concat(callBase),
                        relation: "calls",
                    });
                }
                for (var _j = 0, _k = comp.typeDependencies || []; _j < _k.length; _j++) {
                    var dep = _k[_j];
                    var parts = dep.split(".");
                    var depName = parts.pop();
                    var depMod = parts.join(".");
                    edges.push({
                        from: sourceId,
                        to: "".concat(depMod || compModule, "::").concat(depName),
                        relation: "uses_type",
                    });
                }
            }
            else if (kind === "instance") {
                var className = comp.name.split(" ")[0];
                var classId = "".concat(compModule, "::").concat(className);
                edges.push({ from: sourceId, to: classId, relation: "implements" });
            }
        }
    }
    var allNodeIdsFinal = new Set(nodes.map(function (n) { return n.id; }));
    for (var _l = 0, edges_1 = edges; _l < edges_1.length; _l++) {
        var edge = edges_1[_l];
        for (var _m = 0, _o = ["from", "to"]; _m < _o.length; _m++) {
            var endpoint = _o[_m];
            var edgePoint = edge[endpoint];
            if (!allNodeIdsFinal.has(edgePoint)) {
                nodes.push({
                    id: edgePoint,
                    category: "external",
                    name: edgePoint.split("::").pop(),
                    file_path: "external",
                });
                allNodeIdsFinal.add(edgePoint);
            }
        }
    }
    console.log("Adapted ".concat(nodes.length, " nodes and ").concat(edges.length, " edges"));
    return { nodes: nodes, edges: edges };
}
