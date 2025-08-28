"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.adaptTypeScriptComponents = adaptTypeScriptComponents;
var path = require("path");
function makeNodeId(comp, file_path) {
    var module = file_path;
    if (!module) {
        return null;
    }
    if ((comp.kind === "method" || comp.kind === "field") && comp.class && comp.name) {
        return "".concat(module, "::").concat(comp.class, "::").concat(comp.name);
    }
    if (comp.kind === "namespace" && comp.name) {
        return "".concat(module, "::").concat(comp.name);
    }
    if (comp.name) {
        return "".concat(module, "::").concat(comp.name);
    }
    if (comp.id) {
        return comp.id;
    }
    return null;
}
function adaptTypeScriptComponents(rawComponents) {
    var nodes = [];
    var edges = [];
    var existingNodes = new Set();
    var _loop_1 = function (comp) {
        var kind = comp.kind;
        var node_id = makeNodeId(comp, comp.file_path || "");
        if (!node_id || existingNodes.has(node_id)) {
            return "continue";
        }
        var category = kind !== "namespace" ? kind : "namespace";
        var node = {
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
        Object.keys(node).forEach(function (key) { return node[key] === undefined && delete node[key]; });
        nodes.push(node);
        existingNodes.add(node_id);
        if ((comp.operator === "typeof" || comp.operator === "keyof") && comp.id) {
            var op_node_id = comp.id;
            if (!existingNodes.has(op_node_id)) {
                nodes.push({
                    id: op_node_id,
                    category: comp.operator,
                    label: "".concat(comp.operator, " ").concat(comp.target),
                    target: comp.target,
                    deps: comp.deps,
                    ast_type: comp.ast_type,
                });
                existingNodes.add(op_node_id);
            }
        }
        if (comp.kind === "type_alias" && comp.utility_type) {
            var alias_id = makeNodeId(comp, comp.file_path || "");
            var ut = comp.utility_type;
            var utility_node_id = "utility::".concat(ut.utility_type);
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
            for (var _q = 0, _r = ut.args; _q < _r.length; _q++) {
                var arg = _r[_q];
                var arg_id = arg.includes("::") ? arg : "".concat(comp.module, "::").concat(arg);
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
    };
    for (var _i = 0, rawComponents_1 = rawComponents; _i < rawComponents_1.length; _i++) {
        var comp = rawComponents_1[_i];
        _loop_1(comp);
    }
    for (var _a = 0, rawComponents_2 = rawComponents; _a < rawComponents_2.length; _a++) {
        var comp = rawComponents_2[_a];
        var from_id = makeNodeId(comp, comp.file_path || "");
        if (!from_id)
            continue;
        if (comp.kind === "class" && comp.bases) {
            for (var _b = 0, _c = comp.bases; _b < _c.length; _b++) {
                var base = _c[_b];
                var to_id = "".concat(comp.module, "::").concat(base);
                edges.push({ from: from_id, to: to_id, relation: "extends" });
            }
        }
        if (comp.kind === "interface" && comp.extends) {
            for (var _d = 0, _e = comp.extends; _d < _e.length; _d++) {
                var base = _e[_d];
                var to_id = "".concat(comp.module, "::").concat(base);
                edges.push({ from: from_id, to: to_id, relation: "extends" });
            }
        }
        if (comp.kind === "class" && comp.implements) {
            for (var _f = 0, _g = comp.implements; _f < _g.length; _f++) {
                var iface = _g[_f];
                var to_id = "".concat(comp.module, "::").concat(iface);
                edges.push({ from: from_id, to: to_id, relation: "implements" });
            }
        }
        if (["function", "method", "variable", "function_call", "arrow_function", "generator_function", "generator_function_declaration"].includes(comp.kind || "") && comp.function_calls) {
            var caller_module = from_id.split("::")[0];
            var caller_dir = path.dirname(caller_module);
            for (var _h = 0, _j = comp.function_calls; _h < _j.length; _h++) {
                var call = _j[_h];
                var target_id = call.resolved_callee;
                if (!target_id)
                    continue;
                if (target_id.startsWith(".")) {
                    var _k = target_id.split("::"), target_file = _k[0], target_symbol = _k[1];
                    if (target_file && target_symbol) {
                        var from_file = caller_module;
                        var from_dir = path.dirname(from_file);
                        var combined = path.normalize(path.join(from_dir, target_file)).replace(/\\/g, "/");
                        target_id = "".concat(combined, "::").concat(target_symbol);
                    }
                }
                if (from_id !== target_id) {
                    edges.push({ from: from_id, to: target_id, relation: "calls" });
                }
            }
        }
        if (comp.kind === "type_alias" && comp.type_dependencies) {
            for (var _l = 0, _m = comp.type_dependencies; _l < _m.length; _l++) {
                var dep = _m[_l];
                var to_id = "".concat(comp.module, "::").concat(dep);
                if (from_id !== to_id) {
                    edges.push({ from: from_id, to: to_id, relation: "type_dependency" });
                }
            }
        }
        if ((comp.operator === "typeof" || comp.operator === "keyof") && comp.deps) {
            for (var _o = 0, _p = comp.deps; _o < _p.length; _o++) {
                var dep = _p[_o];
                var to_id = dep.includes("::") ? dep : "".concat(comp.module, "::").concat(dep);
                if (from_id !== to_id) {
                    edges.push({ from: from_id, to: to_id, relation: "fdeps" });
                }
            }
        }
    }
    var filtered_edges = edges.filter(function (e) { return e.from && e.to; });
    return { nodes: nodes, edges: filtered_edges };
}
