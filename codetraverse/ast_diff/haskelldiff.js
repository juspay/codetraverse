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
exports.HaskellFileDiff = void 0;
var Detailedchanges_1 = require("./Detailedchanges");
var basefilediff_1 = require("./basefilediff");
var HaskellFileDiff = /** @class */ (function (_super) {
    __extends(HaskellFileDiff, _super);
    function HaskellFileDiff(moduleName) {
        if (moduleName === void 0) { moduleName = ""; }
        var _this = _super.call(this, moduleName) || this;
        _this.changes = new Detailedchanges_1.DetailedChanges(moduleName);
        return _this;
    }
    HaskellFileDiff.prototype.getDeclName = function (node) {
        if (node.type === 'instance') {
            var instanceHeadNodes = [];
            for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
                var child = _a[_i];
                if (child.type === 'where') {
                    break;
                }
                if (child.type !== 'instance') {
                    instanceHeadNodes.push(child.text);
                }
            }
            return instanceHeadNodes.join(" ").trim();
        }
        if (node.type === 'class') {
            for (var _b = 0, _c = node.children; _b < _c.length; _b++) {
                var child = _c[_b];
                if (child.type === 'name') {
                    return child.text;
                }
            }
            for (var i = 0; i < node.children.length; i++) {
                var child = node.children[i];
                if (child.type === 'class' && i + 1 < node.children.length) {
                    var nextChild = node.children[i + 1];
                    if (['name', 'constructor', 'variable'].includes(nextChild.type)) {
                        return nextChild.text;
                    }
                }
            }
        }
        var queue = __spreadArray([], node.children, true);
        while (queue.length > 0) {
            var current = queue.shift();
            if (['variable', 'constructor'].includes(current.type)) {
                return current.text;
            }
            if (current.isNamed) {
                queue.push.apply(queue, current.children);
            }
        }
        return null;
    };
    HaskellFileDiff.prototype.extractComponents = function (root) {
        var functions = {};
        var data_types = {};
        var type_classes = {};
        var instances = {};
        var imports = {};
        var template_haskell = {};
        var nodeTypeMap = {
            "function": functions,
            "signature": functions,
            "bind": functions,
            "data_type": data_types,
            "class": type_classes,
            "instance": instances,
            "import": imports,
            "top_splice": template_haskell,
        };
        var declarations = [];
        if (root.type === 'haskell') {
            var declarationsNode = root.children.find(function (c) { return c.type === 'declarations'; });
            if (declarationsNode) {
                declarations = declarationsNode.children;
            }
            var importsNode = root.children.find(function (c) { return c.type === 'imports'; });
            if (importsNode) {
                for (var _i = 0, _a = importsNode.children; _i < _a.length; _i++) {
                    var importChild = _a[_i];
                    if (importChild.type === "import") {
                        var name_1 = importChild.text.trim();
                        imports[name_1] = [importChild, importChild.text, importChild.startPosition, importChild.endPosition];
                    }
                }
            }
        }
        for (var _b = 0, declarations_1 = declarations; _b < declarations_1.length; _b++) {
            var child = declarations_1[_b];
            if (child.type in nodeTypeMap && child.type !== "import") {
                var name_2 = this.getDeclName(child);
                if (name_2) {
                    var targetDict = nodeTypeMap[child.type];
                    if (!targetDict[name_2]) {
                        targetDict[name_2] = [child, child.text, child.startPosition, child.endPosition];
                    }
                    else {
                        var _c = targetDict[name_2], existingNode = _c[0], existingText = _c[1], start = _c[2], end = _c[3];
                        var newText = child.text;
                        var combinedText = void 0;
                        var newStart = void 0;
                        var newEnd = void 0;
                        if (child.type === "signature") {
                            combinedText = newText + "\n" + existingText;
                            newStart = child.startPosition;
                            newEnd = end;
                        }
                        else if (existingNode.type === "signature") {
                            combinedText = existingText + "\n" + newText;
                            newStart = start;
                            newEnd = child.endPosition;
                        }
                        else {
                            combinedText = existingText + "\n" + newText;
                            newStart = start;
                            newEnd = child.endPosition;
                        }
                        targetDict[name_2] = [child, combinedText, newStart, newEnd];
                    }
                }
            }
        }
        return [functions, data_types, type_classes, instances, imports, template_haskell];
    };
    return HaskellFileDiff;
}(basefilediff_1.BaseFileDiff));
exports.HaskellFileDiff = HaskellFileDiff;
