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
exports.PythonFileDiff = void 0;
var Detailedchanges_1 = require("./Detailedchanges");
var basefilediff_1 = require("./basefilediff");
var PythonFileDiff = /** @class */ (function (_super) {
    __extends(PythonFileDiff, _super);
    function PythonFileDiff(moduleName) {
        if (moduleName === void 0) { moduleName = ""; }
        var _this = _super.call(this, moduleName) || this;
        _this.changes = new Detailedchanges_1.DetailedChanges(moduleName);
        return _this;
    }
    PythonFileDiff.prototype.getDeclName = function (node) {
        if (node.type === 'decorated_definition') {
            var definition = node.childForFieldName('definition');
            if (definition) {
                return this.getDeclName(definition);
            }
        }
        var nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }
        if (node.type === 'assignment') {
            var leftNode = node.childForFieldName('left');
            if (leftNode && leftNode.type === 'identifier') {
                return leftNode.text;
            }
        }
        return null;
    };
    PythonFileDiff.prototype.extractComponents = function (root) {
        var _a;
        var functions = {};
        var classes = {};
        var imports = {};
        var variables = {};
        var nodeTypeMap = {
            'function_definition': functions,
            'class_definition': classes,
        };
        for (var _i = 0, _b = root.children; _i < _b.length; _i++) {
            var child = _b[_i];
            var nodeToProcess = child;
            if (child.type === 'decorated_definition') {
                var definitionNode = child.childForFieldName('definition');
                if (definitionNode) {
                    nodeToProcess = definitionNode;
                }
            }
            var nodeType = nodeToProcess.type;
            if (nodeType in nodeTypeMap) {
                var name_1 = this.getDeclName(child);
                if (name_1) {
                    var targetDict = nodeTypeMap[nodeType];
                    targetDict[name_1] = [child, child.text, child.startPosition, child.endPosition];
                }
            }
            else if (['import_statement', 'import_from_statement'].includes(nodeType)) {
                var name_2 = child.text;
                imports[name_2] = [child, name_2, child.startPosition, child.endPosition];
            }
            else if (nodeType === 'expression_statement' && ((_a = child.children[0]) === null || _a === void 0 ? void 0 : _a.type) === 'assignment') {
                var assignmentNode = child.children[0];
                var name_3 = this.getDeclName(assignmentNode);
                if (name_3) {
                    variables[name_3] = [child, child.text, child.startPosition, child.endPosition];
                }
            }
        }
        return [functions, classes, imports, variables];
    };
    PythonFileDiff.prototype.diffComponents = function (beforeMap, afterMap) {
        var beforeNames = new Set(Object.keys(beforeMap));
        var afterNames = new Set(Object.keys(afterMap));
        var addedNames = Array.from(afterNames).filter(function (name) { return !beforeNames.has(name); });
        var deletedNames = Array.from(beforeNames).filter(function (name) { return !afterNames.has(name); });
        var commonNames = Array.from(beforeNames).filter(function (name) { return afterNames.has(name); });
        var added = addedNames.sort().map(function (n) { return [n, afterMap[n][1], { start: afterMap[n][2], end: afterMap[n][3] }]; });
        var deleted = deletedNames.sort().map(function (n) { return [n, beforeMap[n][1], { start: beforeMap[n][2], end: beforeMap[n][3] }]; });
        var modified = [];
        for (var _i = 0, _a = commonNames.sort(); _i < _a.length; _i++) {
            var name_4 = _a[_i];
            var _b = beforeMap[name_4], oldAst = _b[0], oldBody = _b[1], oldStart = _b[2], oldEnd = _b[3];
            var _c = afterMap[name_4], newAst = _c[0], newBody = _c[1], newStart = _c[2], newEnd = _c[3];
            if (oldBody.trim() !== newBody.trim()) {
                modified.push([name_4, oldBody, newBody, { old_start: oldStart, old_end: oldEnd, new_start: newStart, new_end: newEnd }]);
            }
        }
        return { added: added, deleted: deleted, modified: modified };
    };
    PythonFileDiff.prototype.compareTwoFiles = function (oldFileAst, newFileAst) {
        var _a = this.extractComponents(oldFileAst), oldFuncs = _a[0], oldClasses = _a[1], oldImports = _a[2], oldVars = _a[3];
        var _b = this.extractComponents(newFileAst), newFuncs = _b[0], newClasses = _b[1], newImports = _b[2], newVars = _b[3];
        var categoryMap = {
            "functions": [oldFuncs, newFuncs],
            "classes": [oldClasses, newClasses],
            "imports": [oldImports, newImports],
            "variables": [oldVars, newVars],
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
    PythonFileDiff.prototype.processSingleFile = function (fileAst, mode) {
        if (mode === void 0) { mode = "deleted"; }
        var _a = this.extractComponents(fileAst), funcs = _a[0], classes = _a[1], imports = _a[2], variables = _a[3];
        var categoryMap = {
            "functions": funcs,
            "classes": classes,
            "imports": imports,
            "variables": variables,
        };
        for (var category in categoryMap) {
            var componentMap = categoryMap[category];
            for (var name_5 in componentMap) {
                var dataTuple = componentMap[name_5];
                var item = [name_5, dataTuple[1], { start: dataTuple[2], end: dataTuple[3] }];
                this.changes.add_change(category, mode, item);
            }
        }
        return this.changes;
    };
    return PythonFileDiff;
}(basefilediff_1.BaseFileDiff));
exports.PythonFileDiff = PythonFileDiff;
