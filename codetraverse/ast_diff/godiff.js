"use strict";
var __extends = (this && this.__extends) || (function () {
    var extendStatics = function (d, b) {
        extendStatics = Object.setPrototypeOf ||
            ({ __proto__: [] } instanceof Array && function (d, b) { d.__proto__ = b; }) ||
            function (d, b) { for (var p in b) if (Object.prototype.hasOwnProperty.call(b, p)) d[p] = b[p]; };
        return extendStatics(d, b);
    };
    return function (d, b) {
        if (typeof b !== "function" && b !== null)
            throw new TypeError("Class extends value " + String(b) + " is not a constructor or null");
        extendStatics(d, b);
        function __() { this.constructor = d; }
        d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
    };
})();
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
exports.GoFileDiff = void 0;
var Detailedchanges_1 = require("./Detailedchanges");
var basefilediff_1 = require("./basefilediff");
var GoFileDiff = /** @class */ (function (_super) {
    __extends(GoFileDiff, _super);
    function GoFileDiff(moduleName) {
        if (moduleName === void 0) { moduleName = ""; }
        var _this = _super.call(this, moduleName) || this;
        _this.changes = new Detailedchanges_1.DetailedChanges(moduleName);
        return _this;
    }
    GoFileDiff.prototype.getDeclName = function (node) {
        if (node.type === 'method_declaration') {
            var receiver = node.childForFieldName('receiver');
            var name_1 = node.childForFieldName('name');
            if (receiver && name_1) {
                return "".concat(receiver.text, " ").concat(name_1.text);
            }
        }
        var nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }
        return null;
    };
    GoFileDiff.prototype.extractComponents = function (root) {
        var functions = {};
        var types = {};
        var variables = {};
        var constants = {};
        var imports = {};
        var topLevelTypes = [
            "function_declaration", "method_declaration", "type_declaration",
            "var_declaration", "const_declaration", "import_declaration",
        ];
        if (root.type === 'source_file') {
            for (var _i = 0, _a = root.children; _i < _a.length; _i++) {
                var child = _a[_i];
                if (topLevelTypes.includes(child.type)) {
                    if (child.type === 'import_declaration') {
                        var queue = __spreadArray([], child.children, true);
                        while (queue.length > 0) {
                            var current = queue.shift();
                            if (current.type === 'import_spec') {
                                var pathNode = current.childForFieldName('path');
                                if (pathNode) {
                                    var name_2 = pathNode.text;
                                    imports[name_2] = [current, current.text, current.startPosition, current.endPosition];
                                }
                            }
                            else {
                                queue.push.apply(queue, current.children);
                            }
                        }
                    }
                    else if (child.type === 'type_declaration') {
                        for (var _b = 0, _c = child.children; _b < _c.length; _b++) {
                            var typeSpec = _c[_b];
                            if (typeSpec.type === 'type_spec') {
                                var name_3 = this.getDeclName(typeSpec);
                                if (name_3) {
                                    types[name_3] = [typeSpec, typeSpec.text, typeSpec.startPosition, typeSpec.endPosition];
                                }
                            }
                        }
                    }
                    else if (child.type === 'var_declaration') {
                        for (var _d = 0, _e = child.children; _d < _e.length; _d++) {
                            var varSpec = _e[_d];
                            if (varSpec.type === 'var_spec') {
                                for (var _f = 0, _g = varSpec.children; _f < _g.length; _f++) {
                                    var nameNode = _g[_f];
                                    if (nameNode.type === 'identifier') {
                                        var name_4 = nameNode.text;
                                        variables[name_4] = [varSpec, varSpec.text, varSpec.startPosition, varSpec.endPosition];
                                    }
                                }
                            }
                        }
                    }
                    else if (child.type === 'const_declaration') {
                        for (var _h = 0, _j = child.children; _h < _j.length; _h++) {
                            var constSpec = _j[_h];
                            if (constSpec.type === 'const_spec') {
                                for (var _k = 0, _l = constSpec.children; _k < _l.length; _k++) {
                                    var nameNode = _l[_k];
                                    if (nameNode.type === 'identifier') {
                                        var name_5 = nameNode.text;
                                        constants[name_5] = [constSpec, constSpec.text, constSpec.startPosition, constSpec.endPosition];
                                    }
                                }
                            }
                        }
                    }
                    else {
                        var name_6 = this.getDeclName(child);
                        if (name_6) {
                            functions[name_6] = [child, child.text, child.startPosition, child.endPosition];
                        }
                    }
                }
            }
        }
        return [functions, types, variables, constants, imports];
    };
    GoFileDiff.prototype.diffComponents = function (beforeMap, afterMap) {
        var beforeNames = new Set(Object.keys(beforeMap));
        var afterNames = new Set(Object.keys(afterMap));
        var addedNames = Array.from(afterNames).filter(function (name) { return !beforeNames.has(name); });
        var deletedNames = Array.from(beforeNames).filter(function (name) { return !afterNames.has(name); });
        var commonNames = Array.from(beforeNames).filter(function (name) { return afterNames.has(name); });
        var added = addedNames.sort().map(function (n) { return [n, afterMap[n][1], { start: afterMap[n][2], end: afterMap[n][3] }]; });
        var deleted = deletedNames.sort().map(function (n) { return [n, beforeMap[n][1], { start: beforeMap[n][2], end: beforeMap[n][3] }]; });
        var modified = [];
        for (var _i = 0, _a = commonNames.sort(); _i < _a.length; _i++) {
            var name_7 = _a[_i];
            var _b = beforeMap[name_7], oldAst = _b[0], oldBody = _b[1], oldStart = _b[2], oldEnd = _b[3];
            var _c = afterMap[name_7], newAst = _c[0], newBody = _c[1], newStart = _c[2], newEnd = _c[3];
            if (oldBody.trim() !== newBody.trim()) {
                modified.push([name_7, oldBody, newBody, { old_start: oldStart, old_end: oldEnd, new_start: newStart, new_end: newEnd }]);
            }
        }
        return { added: added, deleted: deleted, modified: modified };
    };
    GoFileDiff.prototype.compareTwoFiles = function (oldFileAst, newFileAst) {
        var _a = this.extractComponents(oldFileAst), oldFuncs = _a[0], oldTypes = _a[1], oldVars = _a[2], oldConsts = _a[3], oldImports = _a[4];
        var _b = this.extractComponents(newFileAst), newFuncs = _b[0], newTypes = _b[1], newVars = _b[2], newConsts = _b[3], newImports = _b[4];
        var categoryMap = {
            "Functions": [oldFuncs, newFuncs],
            "Types": [oldTypes, newTypes],
            "Vars": [oldVars, newVars],
            "Consts": [oldConsts, newConsts],
            "Imports": [oldImports, newImports],
        };
        for (var category in categoryMap) {
            var _c = categoryMap[category], oldMap = _c[0], newMap = _c[1];
            var diff = this.diffComponents(oldMap, newMap);
            for (var changeType in diff) {
                for (var _i = 0, _d = diff[changeType]; _i < _d.length; _i++) {
                    var item = _d[_i];
                    this.changes.add_change(category.toLowerCase(), changeType, item);
                }
            }
        }
        return this.changes;
    };
    GoFileDiff.prototype.processSingleFile = function (fileAst, mode) {
        if (mode === void 0) { mode = "deleted"; }
        var _a = this.extractComponents(fileAst), funcs = _a[0], types = _a[1], variables = _a[2], constants = _a[3], imports = _a[4];
        var categoryMap = {
            "functions": funcs,
            "types": types,
            "vars": variables,
            "consts": constants,
            "imports": imports,
        };
        for (var category in categoryMap) {
            var componentMap = categoryMap[category];
            for (var name_8 in componentMap) {
                var dataTuple = componentMap[name_8];
                var item = [name_8, dataTuple[1], { start: dataTuple[2], end: dataTuple[3] }];
                this.changes.add_change(category, mode, item);
            }
        }
        return this.changes;
    };
    return GoFileDiff;
}(basefilediff_1.BaseFileDiff));
exports.GoFileDiff = GoFileDiff;
