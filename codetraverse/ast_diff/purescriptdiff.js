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
exports.PureScriptFileDiff = void 0;
var Detailedchanges_1 = require("./Detailedchanges");
var basefilediff_1 = require("./basefilediff");
var PureScriptFileDiff = /** @class */ (function (_super) {
    __extends(PureScriptFileDiff, _super);
    function PureScriptFileDiff(moduleName) {
        if (moduleName === void 0) { moduleName = ""; }
        var _this = _super.call(this, moduleName) || this;
        _this.changes = new Detailedchanges_1.DetailedChanges(moduleName);
        return _this;
    }
    PureScriptFileDiff.prototype.getDeclName = function (node) {
        var nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }
        if (node.type === 'function') {
            if (node.childCount > 0 && node.children[0].type === 'identifier') {
                return node.children[0].text;
            }
        }
        if (node.type === 'type_alias_declaration') {
            var tvbNode = node.children.find(function (c) { return c.type === 'type_variable_binding'; });
            if (tvbNode) {
                var nameNode_1 = tvbNode.children.find(function (c) { return c.type === 'type_identifier'; });
                if (nameNode_1) {
                    return nameNode_1.text;
                }
            }
        }
        if (node.type === 'foreign_import') {
            var nameNode_2 = node.children.find(function (c) { return c.type === 'identifier'; });
            if (nameNode_2) {
                return nameNode_2.text;
            }
        }
        if (node.type === 'class_instance') {
            var instanceNameNode = node.childForFieldName('instance_name');
            if (instanceNameNode) {
                return instanceNameNode.text.trim();
            }
        }
        return null;
    };
    PureScriptFileDiff.prototype.extractComponents = function (root) {
        var items = {
            "functions": {}, "classes": {}, "data_declarations": {},
            "newtypes": {}, "type_aliases": {}, "foreign_imports": {},
            "instances": {},
        };
        var nodeTypeMap = {
            "function": items.functions,
            "class_declaration": items.classes,
            "data_declaration": items.data_declarations,
            "newtype": items.newtypes,
            "type_alias_declaration": items.type_aliases,
            "foreign_import": items.foreign_imports,
            "class_instance": items.instances,
        };
        var queue = [root];
        while (queue.length > 0) {
            var currentNode = queue.shift();
            if (currentNode.type in nodeTypeMap) {
                var name_1 = this.getDeclName(currentNode);
                if (name_1) {
                    var targetDict = nodeTypeMap[currentNode.type];
                    targetDict[name_1] = [currentNode, currentNode.text, currentNode.startPosition, currentNode.endPosition];
                }
            }
            for (var _i = 0, _a = currentNode.children; _i < _a.length; _i++) {
                var child = _a[_i];
                queue.push(child);
            }
        }
        return items;
    };
    PureScriptFileDiff.prototype.deepEqual = function (nodeA, nodeB) {
        if (!nodeA || !nodeB) {
            return nodeA === nodeB;
        }
        if (nodeA.type !== nodeB.type) {
            return false;
        }
        if (nodeA.children.length === 0) {
            return nodeA.text === nodeB.text;
        }
        if (nodeA.children.length !== nodeB.children.length) {
            return false;
        }
        for (var i = 0; i < nodeA.children.length; i++) {
            if (!this.deepEqual(nodeA.children[i], nodeB.children[i])) {
                return false;
            }
        }
        return true;
    };
    PureScriptFileDiff.prototype.diffComponents = function (beforeMap, afterMap) {
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
    PureScriptFileDiff.prototype.compareTwoFiles = function (oldFileAst, newFileAst) {
        var oldItems = this.extractComponents(oldFileAst);
        var newItems = this.extractComponents(newFileAst);
        var allCategories = new Set(__spreadArray(__spreadArray([], Object.keys(oldItems), true), Object.keys(newItems), true));
        for (var _i = 0, _a = Array.from(allCategories); _i < _a.length; _i++) {
            var category = _a[_i];
            var oldMap = oldItems[category] || {};
            var newMap = newItems[category] || {};
            var diff = this.diffComponents(oldMap, newMap);
            for (var changeType in diff) {
                for (var _b = 0, _c = diff[changeType]; _b < _c.length; _b++) {
                    var data = _c[_b];
                    this.changes.add_change(category, changeType, data);
                }
            }
        }
        return this.changes;
    };
    PureScriptFileDiff.prototype.processSingleFile = function (fileAst, mode) {
        if (mode === void 0) { mode = "deleted"; }
        var items = this.extractComponents(fileAst);
        for (var category in items) {
            var componentMap = items[category];
            for (var name_3 in componentMap) {
                var dataTuple = componentMap[name_3];
                var item = [name_3, dataTuple[1], { start: dataTuple[2], end: dataTuple[3] }];
                this.changes.add_change(category, mode, item);
            }
        }
        return this.changes;
    };
    return PureScriptFileDiff;
}(basefilediff_1.BaseFileDiff));
exports.PureScriptFileDiff = PureScriptFileDiff;
