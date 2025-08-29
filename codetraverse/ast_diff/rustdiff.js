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
exports.RustFileDiff = void 0;
var Detailedchanges_1 = require("./Detailedchanges");
var basefilediff_1 = require("./basefilediff");
var RustFileDiff = /** @class */ (function (_super) {
    __extends(RustFileDiff, _super);
    function RustFileDiff(moduleName) {
        if (moduleName === void 0) { moduleName = ""; }
        var _this = _super.call(this, moduleName) || this;
        _this.changes = new Detailedchanges_1.DetailedChanges(moduleName);
        return _this;
    }
    RustFileDiff.prototype.getDeclName = function (node) {
        if (node.type === 'impl_item') {
            var traitNode = node.childForFieldName('trait');
            var typeNode = node.childForFieldName('type');
            if (traitNode && typeNode) {
                return "".concat(traitNode.text, " for ").concat(typeNode.text);
            }
            else if (typeNode) {
                return typeNode.text;
            }
        }
        if (node.type === 'use_declaration') {
            var argNode = node.childForFieldName('argument');
            if (argNode) {
                return argNode.text;
            }
        }
        var nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }
        return null;
    };
    RustFileDiff.prototype.extractComponents = function (root) {
        var items = {
            "functions": {}, "structs": {}, "enums": {}, "traits": {},
            "impls": {}, "uses": {}, "consts": {},
        };
        var nodeTypeMap = {
            "function_item": items.functions,
            "struct_item": items.structs,
            "enum_item": items.enums,
            "trait_item": items.traits,
            "impl_item": items.impls,
            "use_declaration": items.uses,
            "const_item": items.consts,
            "static_item": items.consts,
            "type_item": items.structs,
        };
        if (root.type === 'source_file') {
            for (var _i = 0, _a = root.children; _i < _a.length; _i++) {
                var child = _a[_i];
                if (child.type in nodeTypeMap) {
                    var name_1 = this.getDeclName(child);
                    if (name_1) {
                        var targetDict = nodeTypeMap[child.type];
                        targetDict[name_1] = [child, child.text, child.startPosition, child.endPosition];
                    }
                }
            }
        }
        return items;
    };
    RustFileDiff.prototype.diffComponents = function (beforeMap, afterMap) {
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
            if (oldBody.trim() !== newBody.trim()) {
                modified.push([name_2, oldBody, newBody, { old_start: oldStart, old_end: oldEnd, new_start: newStart, new_end: newEnd }]);
            }
        }
        return { added: added, deleted: deleted, modified: modified };
    };
    RustFileDiff.prototype.compareTwoFiles = function (oldFileAst, newFileAst) {
        var oldItems = this.extractComponents(oldFileAst);
        var newItems = this.extractComponents(newFileAst);
        for (var _i = 0, _a = ["functions", "structs", "enums", "traits", "impls", "uses", "consts"]; _i < _a.length; _i++) {
            var category = _a[_i];
            var diff = this.diffComponents(oldItems[category], newItems[category]);
            for (var changeType in diff) {
                for (var _b = 0, _c = diff[changeType]; _b < _c.length; _b++) {
                    var data = _c[_b];
                    this.changes.add_change(category, changeType, data);
                }
            }
        }
        return this.changes;
    };
    RustFileDiff.prototype.processSingleFile = function (fileAst, mode) {
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
    return RustFileDiff;
}(basefilediff_1.BaseFileDiff));
exports.RustFileDiff = RustFileDiff;
