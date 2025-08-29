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
Object.defineProperty(exports, "__esModule", { value: true });
exports.RescriptFileDiff = void 0;
var child_process_1 = require("child_process");
var Detailedchanges_1 = require("./Detailedchanges");
var basefilediff_1 = require("./basefilediff");
function formatRescriptFile(filePath) {
    try {
        (0, child_process_1.exec)("npx rescript format ".concat(filePath));
    }
    catch (e) {
        // ignore
    }
}
var RescriptFileDiff = /** @class */ (function (_super) {
    __extends(RescriptFileDiff, _super);
    function RescriptFileDiff(moduleName) {
        if (moduleName === void 0) { moduleName = ""; }
        var _this = _super.call(this, moduleName) || this;
        _this.changes = new Detailedchanges_1.DetailedChanges(moduleName);
        return _this;
    }
    RescriptFileDiff.prototype.getDeclName = function (node, nodeType, nameType) {
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (nodeType && child.type === nodeType) {
                for (var _b = 0, _c = child.children; _b < _c.length; _b++) {
                    var grandchild = _c[_b];
                    if (grandchild.isNamed && grandchild.type === nameType) {
                        return grandchild.text;
                    }
                }
            }
            else if (!nodeType && child.isNamed && child.type === nameType) {
                return child.text;
            }
        }
        return null;
    };
    RescriptFileDiff.prototype.deepEqual = function (nodeA, nodeB) {
        var _a, _b;
        if (!nodeA || !nodeB) {
            return nodeA === nodeB;
        }
        if (nodeA.type !== nodeB.type) {
            return false;
        }
        var childrenA = nodeA.children;
        var childrenB = nodeB.children;
        if (childrenA.length !== childrenB.length) {
            return false;
        }
        if (childrenA.length === 0) {
            return nodeA.text === nodeB.text && ((_a = nodeA.parent) === null || _a === void 0 ? void 0 : _a.text) === ((_b = nodeB.parent) === null || _b === void 0 ? void 0 : _b.text);
        }
        for (var i = 0; i < childrenA.length; i++) {
            if (!this.deepEqual(childrenA[i], childrenB[i])) {
                return false;
            }
        }
        return true;
    };
    RescriptFileDiff.prototype.extractComponents = function (root) {
        var _this = this;
        var _a, _b, _c, _d;
        var queue = [root];
        var functions = {};
        var types = {};
        var externals = {};
        var nodeNameMapper = {
            "let_declaration": [functions, function (x) { return _this.getDeclName(x, "let_binding", "value_identifier"); }],
            "type_declaration": [types, function (x) { return _this.getDeclName(x, "type_binding", "type_identifier"); }],
            "external_declaration": [externals, function (x) { return _this.getDeclName(x, null, "value_identifier"); }]
        };
        while (queue.length > 0) {
            var currentNode = queue.pop();
            if (currentNode.type in nodeNameMapper) {
                var _e = nodeNameMapper[currentNode.type], dct = _e[0], mapperFunction = _e[1];
                var name_1 = mapperFunction(currentNode);
                if (name_1) {
                    if (((_a = currentNode.parent) === null || _a === void 0 ? void 0 : _a.type) !== "source_file") {
                        try {
                            name_1 = "".concat((_d = (_c = (_b = currentNode.parent) === null || _b === void 0 ? void 0 : _b.parent) === null || _c === void 0 ? void 0 : _c.child(0)) === null || _d === void 0 ? void 0 : _d.text, "::").concat(name_1);
                        }
                        catch (e) {
                            // ignore
                        }
                    }
                    dct[name_1] = [currentNode, currentNode.text, currentNode.startPosition, currentNode.endPosition];
                }
            }
            else {
                for (var i = currentNode.children.length - 1; i >= 0; i--) {
                    var child = currentNode.children[i];
                    if (child.isNamed) {
                        queue.push(child);
                    }
                }
            }
        }
        return [functions, types, externals];
    };
    RescriptFileDiff.prototype.diffComponents = function (beforeMap, afterMap) {
        var beforeNames = new Set(Object.keys(beforeMap));
        var afterNames = new Set(Object.keys(afterMap));
        var addedNames = Array.from(afterNames).filter(function (name) { return !beforeNames.has(name); });
        var deletedNames = Array.from(beforeNames).filter(function (name) { return !afterNames.has(name); });
        var commonNames = Array.from(beforeNames).filter(function (name) { return afterNames.has(name); });
        var added = addedNames.sort().map(function (n) { return [n, afterMap[n][1], { start: afterMap[n][2], end: afterMap[n][3] }]; });
        var deleted = deletedNames.sort().map(function (n) { return [n, beforeMap[n][1], { start: beforeMap[n][2], end: beforeMap[n][3] }]; });
        var modified = [];
        for (var _i = 0, _a = commonNames.sort(); _i < _a.length; _i++) {
            var name_2 = _a[_i];
            var _b = beforeMap[name_2], oldAst = _b[0], oldBody = _b[1], oldStart = _b[2], oldEnd = _b[3];
            var _c = afterMap[name_2], newAst = _c[0], newBody = _c[1], newStart = _c[2], newEnd = _c[3];
            if (!this.deepEqual(oldAst, newAst)) {
                modified.push([name_2, oldBody, newBody, { old_start: oldStart, old_end: oldEnd, new_start: newStart, new_end: newEnd }]);
            }
        }
        return { added: added, deleted: deleted, modified: modified };
    };
    RescriptFileDiff.prototype.compareTwoFiles = function (oldFileAst, newFileAst) {
        var _a = this.extractComponents(oldFileAst), oldFuncs = _a[0], oldTypes = _a[1], oldExt = _a[2];
        var _b = this.extractComponents(newFileAst), newFuncs = _b[0], newTypes = _b[1], newExt = _b[2];
        var categoryMap = {
            "functions": [oldFuncs, newFuncs],
            "types": [oldTypes, newTypes],
            "externals": [oldExt, newExt],
        };
        for (var category in categoryMap) {
            var _c = categoryMap[category], oldMap = _c[0], newMap = _c[1];
            var diff = this.diffComponents(oldMap, newMap);
            for (var changeType in diff) {
                for (var _i = 0, _d = diff[changeType]; _i < _d.length; _i++) {
                    var item = _d[_i];
                    this.changes.add_change(category, changeType, item);
                }
            }
        }
        return this.changes;
    };
    RescriptFileDiff.prototype.processSingleFile = function (fileAst, mode) {
        if (mode === void 0) { mode = "deleted"; }
        var _a = this.extractComponents(fileAst), funcs = _a[0], types = _a[1], exts = _a[2];
        var funcNames = Object.keys(funcs).sort();
        var typeNames = Object.keys(types).sort();
        var extNames = Object.keys(exts).sort();
        if (mode === "deleted") {
            this.changes.changes['deletedFunctions'] = funcNames.map(function (n) { return [n, funcs[n][1], { start: funcs[n][2], end: funcs[n][3] }]; });
            this.changes.changes['deletedTypes'] = typeNames.map(function (n) { return [n, types[n][1], { start: types[n][2], end: types[n][3] }]; });
            this.changes.changes['deletedExternals'] = extNames.map(function (n) { return [n, exts[n][1], { start: exts[n][2], end: exts[n][3] }]; });
        }
        else {
            this.changes.changes['addedFunctions'] = funcNames.map(function (n) { return [n, funcs[n][1], { start: funcs[n][2], end: funcs[n][3] }]; });
            this.changes.changes['addedTypes'] = typeNames.map(function (n) { return [n, types[n][1], { start: types[n][2], end: types[n][3] }]; });
            this.changes.changes['addedExternals'] = extNames.map(function (n) { return [n, exts[n][1], { start: exts[n][2], end: exts[n][3] }]; });
        }
        return this.changes;
    };
    return RescriptFileDiff;
}(basefilediff_1.BaseFileDiff));
exports.RescriptFileDiff = RescriptFileDiff;
