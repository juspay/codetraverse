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
exports.TypeScriptFileDiff = void 0;
var Detailedchanges_1 = require("./Detailedchanges");
var basefilediff_1 = require("./basefilediff");
var TypeScriptFileDiff = /** @class */ (function (_super) {
    __extends(TypeScriptFileDiff, _super);
    function TypeScriptFileDiff(moduleName) {
        if (moduleName === void 0) { moduleName = ""; }
        var _this = _super.call(this, moduleName) || this;
        _this.changes = new Detailedchanges_1.DetailedChanges(moduleName);
        return _this;
    }
    TypeScriptFileDiff.prototype.getDeclName = function (node) {
        if (node.type === 'export_statement') {
            if (node.namedChildCount > 0) {
                var declarationNode = node.namedChildren[node.namedChildren.length - 1];
                if (declarationNode) {
                    return this.getDeclName(declarationNode);
                }
            }
        }
        if (node.type === 'lexical_declaration') {
            var declaratorNode = node.namedChildren[0];
            if (declaratorNode && declaratorNode.type === 'variable_declarator') {
                var nameNode_1 = declaratorNode.childForFieldName('name');
                if (nameNode_1) {
                    return nameNode_1.text;
                }
            }
        }
        var nameNode = node.childForFieldName('name');
        if (nameNode) {
            return nameNode.text;
        }
        return null;
    };
    TypeScriptFileDiff.prototype.extractClassMethods = function (classNode, className, functionsDict, fieldsDict) {
        var classBody = classNode.children.find(function (c) { return c.type === 'class_body'; });
        if (!classBody) {
            return;
        }
        for (var _i = 0, _a = classBody.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === 'method_definition') {
                var methodNameNode = child.childForFieldName('name');
                if (methodNameNode) {
                    var methodName = methodNameNode.text;
                    var qualifiedName = "".concat(className, ".").concat(methodName);
                    functionsDict[qualifiedName] = [child, child.text, child.startPosition, child.endPosition];
                }
            }
            else if (child.type === 'public_field_definition') {
                var fieldNameNode = child.childForFieldName('name');
                if (fieldNameNode) {
                    var fieldName = fieldNameNode.text;
                    var qualifiedName = "".concat(className, ".").concat(fieldName);
                    fieldsDict[qualifiedName] = [child, child.text, child.startPosition, child.endPosition];
                }
            }
        }
    };
    TypeScriptFileDiff.prototype.extractComponents = function (root) {
        var functions = {};
        var classes = {};
        var interfaces = {};
        var types = {};
        var enums = {};
        var constants = {};
        var fields = {};
        var nodeTypeMap = {
            'function_declaration': functions,
            'class_declaration': classes,
            'interface_declaration': interfaces,
            'type_alias_declaration': types,
            'enum_declaration': enums,
        };
        var declarations = root.type === 'program' ? root.children : [];
        for (var _i = 0, declarations_1 = declarations; _i < declarations_1.length; _i++) {
            var child = declarations_1[_i];
            var nodeToProcess = child;
            if (child.type === 'export_statement') {
                if (child.namedChildCount > 0) {
                    var declarationNode = child.namedChildren[child.namedChildren.length - 1];
                    if (declarationNode) {
                        nodeToProcess = declarationNode;
                    }
                }
            }
            var nodeType = nodeToProcess.type;
            if (nodeType === 'lexical_declaration') {
                var declarator = nodeToProcess.namedChildren[0];
                if (declarator && declarator.type === 'variable_declarator') {
                    var name_1 = this.getDeclName(child);
                    var valueNode = declarator.childForFieldName('value');
                    if (name_1 && valueNode) {
                        var actualValueNode = valueNode;
                        if (actualValueNode.type === 'as_expression' && actualValueNode.childCount > 0) {
                            actualValueNode = actualValueNode.children[0];
                        }
                        if (actualValueNode.type === 'arrow_function') {
                            functions[name_1] = [child, child.text, child.startPosition, child.endPosition];
                        }
                        else if (actualValueNode.type === 'object') {
                            constants[name_1] = [child, child.text, child.startPosition, child.endPosition];
                            for (var _a = 0, _b = actualValueNode.children; _a < _b.length; _a++) {
                                var pairNode = _b[_a];
                                if (pairNode.type === 'pair') {
                                    var keyNode = pairNode.childForFieldName('key');
                                    var valNode = pairNode.childForFieldName('value');
                                    if (keyNode && valNode && valNode.type === 'arrow_function') {
                                        var innerFuncName = "".concat(name_1, ".").concat(keyNode.text);
                                        functions[innerFuncName] = [pairNode, pairNode.text, pairNode.startPosition, pairNode.endPosition];
                                    }
                                }
                            }
                        }
                        else {
                            constants[name_1] = [child, child.text, child.startPosition, child.endPosition];
                        }
                    }
                }
            }
            else if (nodeType in nodeTypeMap) {
                var name_2 = this.getDeclName(child);
                if (name_2) {
                    var targetDict = nodeTypeMap[nodeType];
                    targetDict[name_2] = [child, child.text, child.startPosition, child.endPosition];
                    if (nodeType === 'class_declaration') {
                        this.extractClassMethods(nodeToProcess, name_2, functions, fields);
                    }
                }
            }
        }
        return [functions, classes, interfaces, types, enums, constants, fields];
    };
    TypeScriptFileDiff.prototype.diffComponents = function (beforeMap, afterMap) {
        var beforeNames = new Set(Object.keys(beforeMap));
        var afterNames = new Set(Object.keys(afterMap));
        var addedNames = Array.from(afterNames).filter(function (name) { return !beforeNames.has(name); });
        var deletedNames = Array.from(beforeNames).filter(function (name) { return !afterNames.has(name); });
        var commonNames = Array.from(beforeNames).filter(function (name) { return afterNames.has(name); });
        var added = addedNames.sort().map(function (n) { return [n, afterMap[n][1], { start: afterMap[n][2], end: afterMap[n][3] }]; });
        var deleted = deletedNames.sort().map(function (n) { return [n, beforeMap[n][1], { start: beforeMap[n][2], end: beforeMap[n][3] }]; });
        var modified = [];
        for (var _i = 0, _a = commonNames.sort(); _i < _a.length; _i++) {
            var name_3 = _a[_i];
            var _b = beforeMap[name_3], oldAst = _b[0], oldBody = _b[1], oldStart = _b[2], oldEnd = _b[3];
            var _c = afterMap[name_3], newAst = _c[0], newBody = _c[1], newStart = _c[2], newEnd = _c[3];
            if (oldBody.trim() !== newBody.trim()) {
                modified.push([name_3, oldBody, newBody, { old_start: oldStart, old_end: oldEnd, new_start: newStart, new_end: newEnd }]);
            }
        }
        return { added: added, deleted: deleted, modified: modified };
    };
    TypeScriptFileDiff.prototype.compareTwoFiles = function (oldFileAst, newFileAst) {
        var _a = this.extractComponents(oldFileAst), oldFuncs = _a[0], oldClasses = _a[1], oldIfaces = _a[2], oldTypes = _a[3], oldEnums = _a[4], oldConsts = _a[5], oldFields = _a[6];
        var _b = this.extractComponents(newFileAst), newFuncs = _b[0], newClasses = _b[1], newIfaces = _b[2], newTypes = _b[3], newEnums = _b[4], newConsts = _b[5], newFields = _b[6];
        var categoryMap = {
            "functions": [oldFuncs, newFuncs],
            "classes": [oldClasses, newClasses],
            "interfaces": [oldIfaces, newIfaces],
            "types": [oldTypes, newTypes],
            "enums": [oldEnums, newEnums],
            "constants": [oldConsts, newConsts],
            "fields": [oldFields, newFields],
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
    TypeScriptFileDiff.prototype.processSingleFile = function (fileAst, mode) {
        if (mode === void 0) { mode = "deleted"; }
        var _a = this.extractComponents(fileAst), funcs = _a[0], classes = _a[1], interfaces = _a[2], types = _a[3], enums = _a[4], consts = _a[5], fields = _a[6];
        var categoryMap = {
            "functions": funcs,
            "classes": classes,
            "interfaces": interfaces,
            "types": types,
            "enums": enums,
            "constants": consts,
            "fields": fields,
        };
        for (var category in categoryMap) {
            var componentMap = categoryMap[category];
            for (var name_4 in componentMap) {
                var dataTuple = componentMap[name_4];
                var item = [name_4, dataTuple[1], { start: dataTuple[2], end: dataTuple[3] }];
                this.changes.add_change(category, mode, item);
            }
        }
        return this.changes;
    };
    return TypeScriptFileDiff;
}(basefilediff_1.BaseFileDiff));
exports.TypeScriptFileDiff = TypeScriptFileDiff;
