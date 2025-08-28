"use strict";
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
exports.HaskellComponentExtractor = void 0;
var Parser = require("tree-sitter");
var Haskell = require("tree-sitter-haskell");
var fs = require("fs");
var TOP_LEVEL_KINDS = new Set([
    "header",
    "pragma",
    "import",
    "imports",
    "decl",
    "type_synonym",
    "kind_signature",
    "type_family",
    "type_instance",
    "role_annotation",
    "data_type",
    "newtype",
    "data_family",
    "data_instance",
    "class",
    "instance",
    "default_types",
    "deriving_instance",
    "pattern_synonym",
    "foreign_import",
    "foreign_export",
    "fixity",
    "top_splice",
    "signature",
    "function",
    "bind",
]);
var HaskellComponentExtractor = /** @class */ (function () {
    function HaskellComponentExtractor() {
        this.importMap = {};
        this.allComponents = [];
        this.currentModule = "";
        this.currentFilePath = "";
        this.parser = new Parser();
        this.hsLanguage = Haskell;
        this.parser.setLanguage(this.hsLanguage);
    }
    HaskellComponentExtractor.prototype.processFile = function (filePath) {
        var _this = this;
        // Read file with explicit UTF-8 encoding
        var fileContent = fs.readFileSync(filePath, "utf-8");
        this.currentFilePath = filePath;
        // Check if file is empty or contains only whitespace
        if (fileContent.trim().length === 0) {
            console.log("Skipping empty file: ".concat(filePath));
            return;
        }
        // Validate that the content can be parsed
        var tree;
        try {
            tree = this.parser.parse(fileContent);
        }
        catch (error) {
            // console.error(`Failed to parse file ${filePath}:`, error);
            return;
        }
        if (!tree || !tree.rootNode) {
            console.error("Invalid parse tree for file ".concat(filePath));
            return;
        }
        this.importMap = this.parseImports(tree.rootNode, Buffer.from(fileContent));
        for (var _i = 0, _a = tree.rootNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === "header") {
                var modulePath = [];
                var moduleNode = child.childForFieldName("module");
                if (moduleNode) {
                    for (var _b = 0, _c = moduleNode.children; _b < _c.length; _b++) {
                        var moduleId = _c[_b];
                        if (moduleId.type === "module_id") {
                            modulePath.push(Buffer.from(fileContent).slice(moduleId.startIndex, moduleId.endIndex).toString());
                        }
                    }
                }
                this.currentModule = modulePath.join(".");
                break;
            }
        }
        var rawGroups = tree.rootNode.children.map(function (i) {
            return _this.extractTopLevelComponents(i, Buffer.from(fileContent), _this.importMap);
        });
        this.allComponents = rawGroups.flat();
        for (var _d = 0, _e = this.allComponents; _d < _e.length; _d++) {
            var comp = _e[_d];
            comp.filePath = this.currentFilePath;
        }
        for (var _f = 0, _g = this.allComponents; _f < _g.length; _f++) {
            var comp = _g[_f];
            if (comp.kind === "function") {
                comp.typeDependencies = this.findTypeDependencies(comp.name, this.allComponents);
            }
        }
    };
    HaskellComponentExtractor.prototype.writeToFile = function (outputPath) {
        fs.writeFileSync(outputPath, JSON.stringify(this.allComponents, null, 2), "utf-8");
    };
    HaskellComponentExtractor.prototype.extractAllComponents = function () {
        return this.allComponents;
    };
    HaskellComponentExtractor.prototype.parseImports = function (rootNode, srcBytes) {
        var importMap = {};
        function traverse(node) {
            if (node.type === "import") {
                var moduleNode = node.childForFieldName("module");
                if (moduleNode) {
                    var module_1 = srcBytes
                        .slice(moduleNode.startIndex, moduleNode.endIndex)
                        .toString();
                    var aliasNode = node.childForFieldName("alias");
                    var alias = module_1.split(".").pop();
                    if (aliasNode) {
                        alias = srcBytes
                            .slice(aliasNode.startIndex, aliasNode.endIndex)
                            .toString();
                    }
                    if (!importMap[alias]) {
                        importMap[alias] = [];
                    }
                    importMap[alias].push(module_1);
                }
            }
            for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
                var child = _a[_i];
                traverse(child);
            }
        }
        traverse(rootNode);
        return importMap;
    };
    HaskellComponentExtractor.prototype.extractTopLevelComponents = function (rootNode, srcBytes, importMap) {
        var _a;
        var sigs = {};
        for (var _i = 0, _b = rootNode.children; _i < _b.length; _i++) {
            var child = _b[_i];
            if (child.type === "signature") {
                var start = child.startPosition.row;
                var end = child.endPosition.row;
                var sigCode = srcBytes
                    .toString()
                    .split("\n")
                    .slice(start, end + 1)
                    .join("\n");
                var nameNode = child.childForFieldName("name");
                if (nameNode) {
                    var name_1 = srcBytes
                        .slice(nameNode.startIndex, nameNode.endIndex)
                        .toString();
                    sigs[name_1] = sigCode;
                }
            }
        }
        var components = [];
        if (rootNode.type === "header") {
            var start = rootNode.startPosition.row;
            var end = rootNode.endPosition.row;
            var headerCode = srcBytes
                .toString()
                .split("\n")
                .slice(start, end + 1)
                .join("\n");
            var modulePath = [];
            var modN = rootNode.childForFieldName("module");
            if (modN) {
                for (var _c = 0, _d = modN.namedChildren; _c < _d.length; _c++) {
                    var mid = _d[_c];
                    if (mid.type === "module_id") {
                        modulePath.push(srcBytes.slice(mid.startIndex, mid.endIndex).toString());
                    }
                }
            }
            var exports_1 = [];
            var expN = rootNode.childForFieldName("exports");
            if (expN) {
                for (var _e = 0, _f = expN.namedChildren; _e < _f.length; _e++) {
                    var item = _f[_e];
                    if (item.type === "module_export") {
                        var alias = item.childForFieldName("module");
                        if (alias) {
                            exports_1.push(srcBytes.slice(alias.startIndex, alias.endIndex).toString());
                        }
                    }
                    else if (["export", "import_name", "name"].includes(item.type)) {
                        var txt = srcBytes
                            .slice(item.startIndex, item.endIndex)
                            .toString()
                            .trim();
                        exports_1.push(txt);
                    }
                }
            }
            if (exports_1.length === 0) {
                var parent_1 = rootNode.parent;
                if (parent_1) {
                    for (var _g = 0, _h = parent_1.children; _g < _h.length; _g++) {
                        var sib = _h[_g];
                        for (var _j = 0, _k = sib.children; _j < _k.length; _j++) {
                            var child = _k[_j];
                            if (child.id === rootNode.id)
                                continue;
                            if ([
                                "function",
                                "data_type",
                                "instance",
                                "class",
                                "newtype",
                                "type_synonym",
                            ].includes(child.type)) {
                                var nameN = child.childForFieldName("name") ||
                                    child.childForFieldName("variable");
                                if (nameN) {
                                    exports_1.push(srcBytes.slice(nameN.startIndex, nameN.endIndex).toString());
                                }
                            }
                        }
                    }
                }
            }
            components.push({
                kind: "module_header",
                name: modulePath.join("."),
                startLine: start + 1,
                endLine: end + 1,
                code: headerCode,
                modulePath: modulePath,
                exports: exports_1,
            });
            return components;
        }
        var reexportedModules = {};
        for (var _l = 0, _m = rootNode.children; _l < _m.length; _l++) {
            var child = _m[_l];
            if (child.type === "type_synonym") {
                var name_2 = child.children[1].text;
                var code = child.text;
                components.push({
                    kind: "type_synonym",
                    name: name_2,
                    code: code,
                    startLine: child.startPosition.row + 1,
                    endLine: child.endPosition.row + 1,
                    module: this.currentModule,
                });
            }
            else if (child.type === "bind") {
                var code = child.text;
                var name_3 = child.children[0].text;
                if (name_3) {
                    components.push({
                        kind: ((_a = sigs[name_3]) === null || _a === void 0 ? void 0 : _a.includes("->")) ? "function" : "file_global_variable",
                        name: name_3,
                        code: code,
                        startLine: child.startPosition.row + 1,
                        endLine: child.endPosition.row + 1,
                        module: this.currentModule,
                        typeSignature: sigs[name_3] || null,
                        functionCalls: this.extractFunctionCallsNode(child, srcBytes, importMap, this.currentModule),
                    });
                }
            }
            else if (child.type === "header") {
                console.log("Skipping header node in top-level extraction");
                var start = child.startPosition.row;
                var end = child.endPosition.row;
                var headerCode = srcBytes
                    .toString()
                    .split("\n")
                    .slice(start, end + 1)
                    .join("\n");
                var modulePath = [];
                var moduleNode = child.childForFieldName("module");
                if (moduleNode) {
                    for (var _o = 0, _p = moduleNode.children; _o < _p.length; _o++) {
                        var moduleId = _p[_o];
                        if (moduleId.type === "module_id") {
                            modulePath.push(srcBytes
                                .slice(moduleId.startIndex, moduleId.endIndex)
                                .toString());
                        }
                    }
                }
                components.push({
                    kind: "module_header",
                    name: modulePath.join("."),
                    startLine: start + 1,
                    endLine: end + 1,
                    code: headerCode,
                    modulePath: modulePath,
                });
            }
            else if (child.type === "pragma") {
                var start = child.startPosition.row;
                var end = child.endPosition.row;
                var pragmaCode = srcBytes
                    .toString()
                    .split("\n")
                    .slice(start, end + 1)
                    .join("\n");
                var pragmaContent = pragmaCode
                    .trim()
                    .replace(/^{-#|#-}\s*/g, "")
                    .trim();
                components.push({
                    kind: "pragma",
                    name: pragmaContent,
                    startLine: start + 1,
                    endLine: end + 1,
                    code: pragmaCode,
                });
            }
            else if (child.type === "imports") {
                for (var _q = 0, _r = child.children; _q < _r.length; _q++) {
                    var importNode = _r[_q];
                    if (importNode.type === "import") {
                        var comp = this.extractImportComponent(importNode, srcBytes);
                        if (comp) {
                            components.push(comp);
                        }
                    }
                }
            }
            else if (child.type === "import") {
                var comp = this.extractImportComponent(child, srcBytes);
                if (comp) {
                    components.push(comp);
                }
            }
            else if (child.type === "class") {
                var classComp = this.extractClassComponent(child, srcBytes, importMap);
                if (classComp) {
                    classComp.module = this.currentModule;
                    components.push(classComp);
                }
            }
            else if (child.type === "function") {
                var nameNode = child.childForFieldName("name");
                var fnName = nameNode
                    ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
                    : "unknown";
                var bodyNode = child.childForFieldName("match");
                var bodyCode = bodyNode
                    ? srcBytes.slice(bodyNode.startIndex, bodyNode.endIndex).toString()
                    : "";
                var start = child.startPosition.row;
                var end = child.endPosition.row;
                var entireFuncCode = srcBytes
                    .toString()
                    .split("\n")
                    .slice(start, end + 1)
                    .join("\n");
                var comp = {
                    kind: "function",
                    name: fnName,
                    module: this.currentModule,
                    startLine: start + 1,
                    endLine: end + 1,
                    code: entireFuncCode,
                };
                if (fnName && sigs[fnName]) {
                    comp.typeSignature = sigs[fnName];
                }
                if (bodyNode) {
                    comp.functionCalls = this.extractFunctionCallsNode(bodyNode, srcBytes, importMap, this.currentModule);
                }
                else {
                    comp.functionCalls = [];
                }
                var whereDefs = this.extractWhereDefinitions(child, srcBytes);
                if (whereDefs.length > 0) {
                    comp.whereDefinitions = whereDefs;
                    for (var _s = 0, whereDefs_1 = whereDefs; _s < whereDefs_1.length; _s++) {
                        var whereDef = whereDefs_1[_s];
                        if (whereDef.kind === "function") {
                            whereDef.functionCalls = this.extractFunctionCallsNode(child, srcBytes, importMap, this.currentModule);
                        }
                    }
                }
                components.push(comp);
                comp.reexportedFrom = reexportedModules[this.currentModule] || [];
            }
            else if (child.type === "instance") {
                var instanceComp = this.extractInstanceComponent(child, srcBytes, importMap);
                if (instanceComp) {
                    instanceComp.module = this.currentModule;
                    instanceComp.functionCalls = this.extractFunctionCallsNode(child, srcBytes, importMap, this.currentModule);
                    components.push(instanceComp);
                }
            }
            else if (child.type === "data_type") {
                var dataComp = this.extractDataTypeComponent(child, srcBytes, importMap);
                if (dataComp) {
                    dataComp.module = this.currentModule;
                    dataComp.functionCalls = this.extractFunctionCallsNode(child, srcBytes, importMap, this.currentModule);
                    components.push(dataComp);
                }
            }
        }
        for (var _t = 0, components_1 = components; _t < components_1.length; _t++) {
            var comp = components_1[_t];
            if (comp.kind === "import" && comp.alias && comp.module) {
                if (!reexportedModules[comp.module]) {
                    reexportedModules[comp.module] = [];
                }
                reexportedModules[comp.module].push(comp.alias);
            }
        }
        return components;
    };
    HaskellComponentExtractor.prototype.extractClassComponent = function (classNode, srcBytes, importMap) {
        var start = classNode.startPosition.row;
        var end = classNode.endPosition.row;
        var classCode = srcBytes
            .toString()
            .split("\n")
            .slice(start, end + 1)
            .join("\n");
        var nameNode = classNode.childForFieldName("name");
        var className = nameNode
            ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
            : "UnknownClass";
        var typeParams = [];
        var patternsNode = classNode.childForFieldName("patterns");
        if (patternsNode) {
            for (var _i = 0, _a = patternsNode.children; _i < _a.length; _i++) {
                var paramNode = _a[_i];
                if (paramNode.type === "variable") {
                    var paramName = srcBytes
                        .slice(paramNode.startIndex, paramNode.endIndex)
                        .toString();
                    typeParams.push(paramName);
                }
            }
        }
        var declarations = [];
        var declarationsNode = classNode.childForFieldName("declarations");
        if (declarationsNode) {
            for (var _b = 0, _c = declarationsNode.children; _b < _c.length; _b++) {
                var declNode = _c[_b];
                if (declNode.type === "declaration") {
                    for (var _d = 0, _e = declNode.children; _d < _e.length; _d++) {
                        var innerDecl = _e[_d];
                        var declInfo = this.extractClassDeclaration(innerDecl, srcBytes);
                        if (declInfo) {
                            declarations.push(declInfo);
                        }
                    }
                }
                else {
                    var declInfo = this.extractClassDeclaration(declNode, srcBytes);
                    if (declInfo) {
                        declarations.push(declInfo);
                    }
                }
            }
        }
        var constraints = [];
        for (var _f = 0, _g = classNode.children; _f < _g.length; _f++) {
            var child = _g[_f];
            if (child.type === "context") {
                constraints = this.extractClassConstraints(child, srcBytes);
            }
        }
        var typeFamilies = declarations.filter(function (d) { return d.declarationType === "type_family"; });
        var methodSigs = declarations.filter(function (d) { return d.declarationType === "method_signature"; });
        var defaultMethods = declarations.filter(function (d) { return d.declarationType === "default_method"; });
        return {
            kind: "class",
            name: className,
            startLine: start + 1,
            endLine: end + 1,
            code: classCode,
            typeParameters: typeParams,
            constraints: constraints,
            declarations: declarations,
            typeFamilies: typeFamilies,
            methodSignatures: methodSigs,
            defaultMethods: defaultMethods,
        };
    };
    HaskellComponentExtractor.prototype.extractClassDeclaration = function (declNode, srcBytes) {
        var declStart = declNode.startPosition.row;
        var declEnd = declNode.endPosition.row;
        var declCode = srcBytes
            .toString()
            .split("\n")
            .slice(declStart, declEnd + 1)
            .join("\n");
        if (declNode.type === "type_family") {
            var nameNode = declNode.childForFieldName("name");
            var familyName = nameNode
                ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
                : "UnknownTypeFamily";
            var familyParams = [];
            var patternsNode = declNode.childForFieldName("patterns");
            if (patternsNode) {
                for (var _i = 0, _a = patternsNode.children; _i < _a.length; _i++) {
                    var paramNode = _a[_i];
                    if (paramNode.type === "variable") {
                        var paramName = srcBytes
                            .slice(paramNode.startIndex, paramNode.endIndex)
                            .toString();
                        familyParams.push(paramName);
                    }
                }
            }
            return {
                declarationType: "type_family",
                name: familyName,
                parameters: familyParams,
                code: declCode.trim(),
                startLine: declStart + 1,
                endLine: declEnd + 1,
            };
        }
        else if (declNode.type === "signature") {
            var nameNode = declNode.childForFieldName("name");
            var methodName = nameNode
                ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
                : "UnknownMethod";
            var typeNode = declNode.childForFieldName("type");
            var typeSig = typeNode
                ? srcBytes.slice(typeNode.startIndex, typeNode.endIndex).toString()
                : "";
            return {
                declarationType: "method_signature",
                name: methodName,
                typeSignature: typeSig,
                code: declCode.trim(),
                startLine: declStart + 1,
                endLine: declEnd + 1,
            };
        }
        else if (declNode.type === "function") {
            var nameNode = declNode.childForFieldName("name");
            var methodName = nameNode
                ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
                : "UnknownMethod";
            return {
                declarationType: "default_method",
                name: methodName,
                code: declCode.trim(),
                startLine: declStart + 1,
                endLine: declEnd + 1,
            };
        }
        else {
            return {
                declarationType: declNode.type,
                code: declCode.trim(),
                startLine: declStart + 1,
                endLine: declEnd + 1,
            };
        }
    };
    HaskellComponentExtractor.prototype.extractClassConstraints = function (contextNode, srcBytes) {
        var constraints = [];
        for (var _i = 0, _a = contextNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === "constraint") {
                var constraintText = srcBytes
                    .slice(child.startIndex, child.endIndex)
                    .toString();
                constraints.push(constraintText);
            }
        }
        return constraints;
    };
    HaskellComponentExtractor.prototype.extractFunctionCallsNode = function (functionNode, srcBytes, importMap, currentModule) {
        var _this = this;
        var identifiers = [];
        var currentFileFunctions = new Set(this.allComponents
            .filter(function (c) { return c.kind === "function"; })
            .map(function (c) { return c.name; }));
        var traverseNode = function (node) {
            if (node.type === "qualified") {
                var moduleNode = node.childForFieldName("module");
                var idNode = node.childForFieldName("id") || node.childForFieldName("variable");
                if (moduleNode && idNode) {
                    var moduleParts_1 = [];
                    for (var _i = 0, _a = moduleNode.children; _i < _a.length; _i++) {
                        var child = _a[_i];
                        if (child.type === "module_id") {
                            moduleParts_1.push(srcBytes.slice(child.startIndex, child.endIndex).toString());
                        }
                    }
                    var prefix = moduleParts_1.join(".");
                    var baseName = srcBytes
                        .slice(idNode.startIndex, idNode.endIndex)
                        .toString();
                    var resolvedModules = [prefix];
                    if (moduleParts_1.length > 0) {
                        var firstComponent = moduleParts_1[0];
                        if (importMap[firstComponent]) {
                            var resolved = importMap[firstComponent];
                            if (moduleParts_1.length > 1) {
                                resolved = resolved.map(function (r) { return "".concat(r, ".").concat(moduleParts_1.slice(1).join(".")); });
                            }
                            resolvedModules = resolved;
                        }
                    }
                    identifiers.push({
                        name: "".concat(prefix, ".").concat(baseName),
                        type: "qualified",
                        modules: resolvedModules,
                        base: baseName,
                        context: "function_call",
                    });
                }
            }
            else if (node.type === "variable") {
                if (!_this._is_in_binding_position(node)) {
                    var varName = srcBytes
                        .slice(node.startIndex, node.endIndex)
                        .toString();
                    var skipKeywords = new Set([
                        "if",
                        "then",
                        "else",
                        "let",
                        "in",
                        "do",
                        "case",
                        "of",
                        "where",
                        "data",
                        "type",
                        "newtype",
                        "class",
                        "instance",
                        "deriving",
                        "import",
                        "module",
                        "as",
                        "hiding",
                        "qualified",
                        "infix",
                        "infixl",
                        "infixr",
                        "pure",
                        "return",
                        "mempty",
                        "mappend",
                    ]);
                    if (!skipKeywords.has(varName)) {
                        identifiers.push({
                            name: varName,
                            type: "function",
                            modules: [currentModule],
                            base: varName,
                            context: "function_call",
                            localFunction: currentFileFunctions.has(varName),
                        });
                    }
                }
            }
            else if (node.type === "constructor") {
                var ctorName = srcBytes
                    .slice(node.startIndex, node.endIndex)
                    .toString();
                identifiers.push({
                    name: ctorName,
                    type: "type_constructor",
                    context: "type_system",
                });
            }
            else if (node.type === "operator") {
                var opName = srcBytes
                    .slice(node.startIndex, node.endIndex)
                    .toString();
                identifiers.push({
                    name: opName,
                    type: "operator",
                    context: "operation",
                });
            }
            else if (node.type === "integer") {
                var numVal = srcBytes
                    .slice(node.startIndex, node.endIndex)
                    .toString();
                identifiers.push({
                    name: numVal,
                    type: "literal",
                    subtype: "numeric",
                    value: numVal,
                    context: "literal",
                });
            }
            else if (node.type === "float") {
                var numVal = srcBytes
                    .slice(node.startIndex, node.endIndex)
                    .toString();
                identifiers.push({
                    name: numVal,
                    type: "literal",
                    subtype: "numeric",
                    value: numVal,
                    context: "literal",
                });
            }
            else if (node.type === "string") {
                var strVal = srcBytes
                    .slice(node.startIndex, node.endIndex)
                    .toString();
                identifiers.push({
                    name: strVal,
                    type: "literal",
                    subtype: "string",
                    context: "literal",
                });
            }
            else if (node.type === "list") {
                var listContent = srcBytes
                    .slice(node.startIndex, node.endIndex)
                    .toString();
                identifiers.push({
                    name: listContent,
                    type: "literal",
                    subtype: "list",
                    context: "literal",
                });
            }
            else if (node.type === "tuple") {
                var tupleContent = srcBytes
                    .slice(node.startIndex, node.endIndex)
                    .toString();
                var elementCount = (tupleContent.match(/,/g) || []).length + 1 > 1
                    ? (tupleContent.match(/,/g) || []).length + 1
                    : 2;
                identifiers.push({
                    name: tupleContent,
                    type: "literal",
                    subtype: "tuple",
                    length: elementCount,
                    context: "literal",
                });
            }
            else if (node.type === "lambda") {
                identifiers.push({
                    name: "λ",
                    type: "lambda",
                    context: "anonymous_function",
                });
            }
            for (var _b = 0, _c = node.children; _b < _c.length; _b++) {
                var child = _c[_b];
                traverseNode(child);
            }
        };
        traverseNode(functionNode);
        var seen = new Set();
        var uniqueIdentifiers = [];
        for (var _i = 0, identifiers_1 = identifiers; _i < identifiers_1.length; _i++) {
            var ident = identifiers_1[_i];
            var key = "".concat(ident.name, ",").concat(ident.type, ",").concat(ident.context);
            if (!seen.has(key)) {
                seen.add(key);
                uniqueIdentifiers.push(ident);
            }
        }
        return uniqueIdentifiers;
    };
    HaskellComponentExtractor.prototype._is_in_binding_position = function (node) {
        var parent = node.parent;
        if (!parent) {
            return false;
        }
        if (parent.type === "bind") {
            var nameField = parent.childForFieldName("name");
            if (nameField && nameField.id === node.id) {
                return true;
            }
        }
        else if (parent.type === "function") {
            var nameField = parent.childForFieldName("name");
            if (nameField && nameField.id === node.id) {
                return true;
            }
            var patternsField = parent.childForFieldName("patterns");
            if (patternsField && this._node_contains_child(patternsField, node)) {
                return true;
            }
        }
        else if (["patterns", "pattern"].includes(parent.type)) {
            return true;
        }
        else if (parent.type === "signature") {
            var nameField = parent.childForFieldName("name");
            if (nameField && nameField.id === node.id) {
                return true;
            }
        }
        else if (parent.type === "local_binds") {
            return this._is_in_binding_position(parent);
        }
        return false;
    };
    HaskellComponentExtractor.prototype._node_contains_child = function (parentNode, targetNode) {
        if (parentNode.id === targetNode.id) {
            return true;
        }
        for (var _i = 0, _a = parentNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (this._node_contains_child(child, targetNode)) {
                return true;
            }
        }
        return false;
    };
    HaskellComponentExtractor.prototype.extractWhereDefinitions = function (functionNode, srcBytes) {
        var whereDefs = [];
        for (var _i = 0, _a = functionNode.children; _i < _a.length; _i++) {
            var node = _a[_i];
            if (node.type === "local_binds") {
                for (var _b = 0, _c = node.children; _b < _c.length; _b++) {
                    var bindNode = _c[_b];
                    if (bindNode.type !== "bind")
                        continue;
                    var nameNode = bindNode.childForFieldName("name");
                    if (!nameNode)
                        continue;
                    var name_4 = srcBytes
                        .slice(nameNode.startIndex, nameNode.endIndex)
                        .toString();
                    var start = bindNode.startPosition.row;
                    var end = bindNode.endPosition.row;
                    var code = srcBytes
                        .toString()
                        .split("\n")
                        .slice(start, end + 1)
                        .join("\n");
                    whereDefs.push({
                        kind: "function",
                        name: name_4,
                        code: code,
                    });
                }
            }
        }
        return whereDefs;
    };
    HaskellComponentExtractor.prototype.extractImportComponent = function (importNode, srcBytes) {
        var start = importNode.startPosition.row;
        var end = importNode.endPosition.row;
        var importCode = srcBytes
            .toString()
            .split("\n")
            .slice(start, end + 1)
            .join("\n");
        var moduleNode = importNode.childForFieldName("module");
        var moduleName = moduleNode
            ? srcBytes.slice(moduleNode.startIndex, moduleNode.endIndex).toString()
            : null;
        var aliasNode = importNode.childForFieldName("alias");
        var alias = aliasNode
            ? srcBytes.slice(aliasNode.startIndex, aliasNode.endIndex).toString()
            : null;
        var importList = [];
        var namesNode = importNode.childForFieldName("names");
        if (namesNode) {
            for (var _i = 0, _a = namesNode.children; _i < _a.length; _i++) {
                var nameChild = _a[_i];
                if (nameChild.type === "import_name") {
                    for (var _b = 0, _c = nameChild.children; _b < _c.length; _b++) {
                        var idChild = _c[_b];
                        if (["name", "variable"].includes(idChild.type)) {
                            importList.push(srcBytes.slice(idChild.startIndex, idChild.endIndex).toString());
                        }
                    }
                }
            }
        }
        var isQualified = importCode.includes("qualified");
        var isHiding = importCode.includes("hiding");
        if (!moduleName)
            return null;
        return {
            kind: "import",
            name: moduleName,
            module: moduleName,
            alias: alias,
            importList: importList,
            isQualified: isQualified,
            isHiding: isHiding,
            startLine: start + 1,
            endLine: end + 1,
            code: importCode,
        };
    };
    HaskellComponentExtractor.prototype.extractDataTypeComponent = function (dataNode, srcBytes, importMap) {
        var start = dataNode.startPosition.row;
        var end = dataNode.endPosition.row;
        var dataCode = srcBytes
            .toString()
            .split("\n")
            .slice(start, end + 1)
            .join("\n");
        var dataName = this.extractDataTypeName(dataNode, srcBytes);
        var constructors = [];
        for (var _i = 0, _a = dataNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === "data_constructors") {
                constructors = this.extractDataConstructors(child, srcBytes);
            }
        }
        var derivingInfo = null;
        for (var _b = 0, _c = dataNode.children; _b < _c.length; _b++) {
            var child = _c[_b];
            if (child.type === "deriving") {
                derivingInfo = this.extractDerivingClause(child, srcBytes);
            }
        }
        return {
            kind: "data_type",
            name: dataName,
            startLine: start + 1,
            endLine: end + 1,
            code: dataCode,
            constructors: constructors,
            deriving: derivingInfo,
        };
    };
    HaskellComponentExtractor.prototype.extractDataTypeName = function (dataNode, srcBytes) {
        var nameNode = dataNode.childForFieldName("name");
        if (nameNode) {
            return srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString();
        }
        return "UnknownDataType";
    };
    HaskellComponentExtractor.prototype.extractDataConstructors = function (constructorsNode, srcBytes) {
        var constructors = [];
        for (var _i = 0, _a = constructorsNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === "data_constructor") {
                var constructor = this.extractSingleConstructor(child, srcBytes);
                if (constructor) {
                    constructors.push(constructor);
                }
            }
        }
        return constructors;
    };
    HaskellComponentExtractor.prototype.extractSingleConstructor = function (constructorNode, srcBytes) {
        var constructorInfo = {
            type: "constructor",
            name: "Unknown",
            fields: [],
        };
        for (var _i = 0, _a = constructorNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === "record") {
                constructorInfo.type = "record";
                constructorInfo.name = this.extractConstructorName(child, srcBytes);
                constructorInfo.fields = this.extractRecordFields(child, srcBytes);
            }
            else if (child.type === "constructor") {
                constructorInfo.name = srcBytes
                    .slice(child.startIndex, child.endIndex)
                    .toString();
            }
        }
        return constructorInfo;
    };
    HaskellComponentExtractor.prototype.extractConstructorName = function (recordNode, srcBytes) {
        var nameNode = recordNode.childForFieldName("constructor");
        if (nameNode) {
            return srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString();
        }
        return "UnknownConstructor";
    };
    HaskellComponentExtractor.prototype.extractRecordFields = function (recordNode, srcBytes) {
        var fields = [];
        var fieldsNode = recordNode.childForFieldName("fields");
        if (fieldsNode) {
            for (var _i = 0, _a = fieldsNode.children; _i < _a.length; _i++) {
                var fieldChild = _a[_i];
                if (fieldChild.type === "field") {
                    var fieldInfo = this.extractFieldInfo(fieldChild, srcBytes);
                    if (fieldInfo) {
                        fields.push(fieldInfo);
                    }
                }
            }
        }
        return fields;
    };
    HaskellComponentExtractor.prototype.extractFieldInfo = function (fieldNode, srcBytes) {
        var nameNode = fieldNode.childForFieldName("name");
        var fieldName = nameNode
            ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
            : null;
        var typeNode = fieldNode.childForFieldName("type");
        var typeTxt = typeNode
            ? srcBytes.slice(typeNode.startIndex, typeNode.endIndex).toString()
            : null;
        var core = typeTxt;
        if (core && core.includes(" ")) {
            core = core.split(" ").pop();
        }
        var typeInfo;
        if (core && core.includes(".")) {
            var parts = core.split(".");
            var base_1 = parts.pop();
            var modulePart = parts.join(".");
            var resolved = this.importMap[modulePart] || [modulePart];
            var modules = resolved.map(function (m) { return "".concat(m, ".").concat(base_1); });
            typeInfo = {
                name: "".concat(modulePart, ".").concat(base_1),
                type: "qualified",
                modules: modules,
                base: base_1,
                context: "type_constructor",
            };
        }
        else {
            typeInfo = {
                name: core,
                type: "simple",
                modules: [],
                base: core,
                context: "type_constructor",
            };
        }
        return {
            name: fieldName,
            type: typeTxt,
            typeInfo: typeInfo,
        };
    };
    HaskellComponentExtractor.prototype._extractQualifiedType = function (qualifiedNode, srcBytes) {
        var moduleBits = [];
        var moduleNode = qualifiedNode.childForFieldName("module");
        if (moduleNode) {
            for (var _i = 0, _a = moduleNode.children; _i < _a.length; _i++) {
                var m = _a[_i];
                if (m.type === "module_id") {
                    moduleBits.push(srcBytes.slice(m.startIndex, m.endIndex).toString());
                }
            }
        }
        var baseNode = qualifiedNode.childForFieldName("id") ||
            qualifiedNode.childForFieldName("name");
        var base = baseNode
            ? srcBytes.slice(baseNode.startIndex, baseNode.endIndex).toString()
            : "";
        var full = __spreadArray(__spreadArray([], moduleBits, true), [base], false).filter(Boolean).join(".");
        var first = moduleBits.length > 0 ? moduleBits[0] : null;
        var modules;
        if (first && this.importMap[first]) {
            modules = this.importMap[first].map(function (imp) { return "".concat(imp, ".").concat(moduleBits.slice(1).join(".")); });
        }
        else {
            modules = moduleBits.length > 0 ? [moduleBits.join(".")] : [];
        }
        return { full: full, modules: modules, base: base };
    };
    HaskellComponentExtractor.prototype.extractTypeInfo = function (typeNode, srcBytes) {
        if (typeNode.type === "name") {
            return srcBytes.slice(typeNode.startIndex, typeNode.endIndex).toString();
        }
        else if (typeNode.type === "qualified") {
            return this.extractQualifiedType(typeNode, srcBytes);
        }
        else if (typeNode.type === "apply") {
            return this.extractAppliedType(typeNode, srcBytes);
        }
        else {
            return srcBytes.slice(typeNode.startIndex, typeNode.endIndex).toString();
        }
    };
    HaskellComponentExtractor.prototype.extractQualifiedType = function (qualifiedNode, srcBytes) {
        var modulePart = "";
        var idPart = "";
        var moduleNode = qualifiedNode.childForFieldName("module");
        if (moduleNode) {
            for (var _i = 0, _a = moduleNode.children; _i < _a.length; _i++) {
                var moduleChild = _a[_i];
                if (moduleChild.type === "module_id") {
                    modulePart = srcBytes
                        .slice(moduleChild.startIndex, moduleChild.endIndex)
                        .toString();
                }
            }
        }
        var baseNode = qualifiedNode.childForFieldName("id") ||
            qualifiedNode.childForFieldName("name");
        if (baseNode) {
            idPart = srcBytes.slice(baseNode.startIndex, baseNode.endIndex).toString();
        }
        return modulePart && idPart ? "".concat(modulePart, ".").concat(idPart) : idPart;
    };
    HaskellComponentExtractor.prototype.extractAppliedType = function (applyNode, srcBytes) {
        var constructor = "";
        var argument = "";
        for (var _i = 0, _a = applyNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === "name") {
                constructor = srcBytes
                    .slice(child.startIndex, child.endIndex)
                    .toString();
            }
            else if (["qualified", "name"].includes(child.type)) {
                argument = this.extractTypeInfo(child, srcBytes);
            }
        }
        return constructor && argument ? "".concat(constructor, " ").concat(argument) : constructor;
    };
    HaskellComponentExtractor.prototype.extractDerivingClause = function (derivingNode, srcBytes) {
        var derivingInfo = {
            strategy: null,
            classes: [],
        };
        for (var _i = 0, _a = derivingNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === "deriving_strategy") {
                derivingInfo.strategy = srcBytes
                    .slice(child.startIndex, child.endIndex)
                    .toString();
            }
            else if (child.type === "tuple") {
                for (var _b = 0, _c = child.children; _b < _c.length; _b++) {
                    var tupleChild = _c[_b];
                    if (tupleChild.type === "name") {
                        var className = srcBytes
                            .slice(tupleChild.startIndex, tupleChild.endIndex)
                            .toString();
                        derivingInfo.classes.push(className);
                    }
                }
            }
        }
        return derivingInfo;
    };
    HaskellComponentExtractor.prototype.extractInstanceComponent = function (instanceNode, srcBytes, importMap) {
        var start = instanceNode.startPosition.row;
        var end = instanceNode.endPosition.row;
        var instanceCode = srcBytes
            .toString()
            .split("\n")
            .slice(start, end + 1)
            .join("\n");
        var instanceName = this.extractInstanceName(instanceNode, srcBytes);
        var typePatterns = this.extractTypePatterns(instanceNode, srcBytes);
        var instanceMethods = [];
        var typeInstances = [];
        for (var _i = 0, _a = instanceNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === "instance_declarations") {
                for (var _b = 0, _c = child.children; _b < _c.length; _b++) {
                    var decl = _c[_b];
                    if (decl.type === "declaration") {
                        for (var _d = 0, _e = decl.children; _d < _e.length; _d++) {
                            var innerDecl = _e[_d];
                            if (innerDecl.type === "bind") {
                                var method = this.extractInstanceMethod(innerDecl, srcBytes, importMap);
                                if (method) {
                                    instanceMethods.push(method);
                                }
                            }
                            else if (innerDecl.type === "type_instance") {
                                var typeInst = this.extractTypeInstance(innerDecl, srcBytes);
                                if (typeInst) {
                                    typeInstances.push(typeInst);
                                }
                            }
                        }
                    }
                }
            }
        }
        return {
            kind: "instance",
            name: instanceName,
            startLine: start + 1,
            endLine: end + 1,
            code: instanceCode,
            typePatterns: typePatterns,
            instanceMethods: instanceMethods,
            typeInstances: typeInstances,
        };
    };
    HaskellComponentExtractor.prototype.extractInstanceName = function (instanceNode, srcBytes) {
        var nameNode = instanceNode.childForFieldName("name");
        if (nameNode) {
            return srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString();
        }
        return "UnknownInstance";
    };
    HaskellComponentExtractor.prototype.extractTypePatterns = function (instanceNode, srcBytes) {
        var patterns = [];
        var typePatternsNode = instanceNode.childForFieldName("type_patterns");
        if (typePatternsNode) {
            for (var _i = 0, _a = typePatternsNode.children; _i < _a.length; _i++) {
                var pattern = _a[_i];
                if (pattern.type === "qualified") {
                    var qualifiedInfo = this.extractQualifiedInfo(pattern, srcBytes);
                    patterns.push(qualifiedInfo);
                }
                else {
                    var patternText = srcBytes
                        .slice(pattern.startIndex, pattern.endIndex)
                        .toString();
                    patterns.push({
                        name: patternText,
                        type: "simple",
                        context: "type_pattern",
                    });
                }
            }
        }
        return patterns;
    };
    HaskellComponentExtractor.prototype.extractQualifiedInfo = function (qualifiedNode, srcBytes) {
        var modulePart = "";
        var idPart = "";
        var moduleNode = qualifiedNode.childForFieldName("module");
        if (moduleNode) {
            for (var _i = 0, _a = moduleNode.children; _i < _a.length; _i++) {
                var moduleChild = _a[_i];
                if (moduleChild.type === "module_id") {
                    modulePart = srcBytes
                        .slice(moduleChild.startIndex, moduleChild.endIndex)
                        .toString();
                }
            }
        }
        var baseNode = qualifiedNode.childForFieldName("id") ||
            qualifiedNode.childForFieldName("name");
        if (baseNode) {
            idPart = srcBytes.slice(baseNode.startIndex, baseNode.endIndex).toString();
        }
        if (modulePart && idPart) {
            var fullName = "".concat(modulePart, ".").concat(idPart);
            var resolvedModules = this.importMap[modulePart] || [modulePart];
            return {
                name: fullName,
                type: "qualified",
                modules: resolvedModules,
                base: idPart,
                context: "type_pattern",
            };
        }
        else if (idPart) {
            return {
                name: idPart,
                type: "simple",
                context: "type_pattern",
            };
        }
        else {
            var fallbackName = srcBytes
                .slice(qualifiedNode.startIndex, qualifiedNode.endIndex)
                .toString();
            return {
                name: fallbackName,
                type: "fallback",
                context: "type_pattern",
            };
        }
    };
    HaskellComponentExtractor.prototype.extractInstanceMethod = function (bindNode, srcBytes, importMap) {
        var methodName = "";
        var nameNode = bindNode.childForFieldName("name");
        if (nameNode) {
            methodName = srcBytes
                .slice(nameNode.startIndex, nameNode.endIndex)
                .toString();
        }
        var start = bindNode.startPosition.row;
        var end = bindNode.endPosition.row;
        var methodCode = srcBytes
            .toString()
            .split("\n")
            .slice(start, end + 1)
            .join("\n");
        return {
            kind: "instance_method",
            name: methodName,
            code: methodCode.trim(),
        };
    };
    HaskellComponentExtractor.prototype.extractTypeInstance = function (typeInstanceNode, srcBytes) {
        var typeName = "";
        var nameNode = typeInstanceNode.childForFieldName("name");
        if (nameNode) {
            typeName = srcBytes
                .slice(nameNode.startIndex, nameNode.endIndex)
                .toString();
        }
        var typePatterns = [];
        var typePatternsNode = typeInstanceNode.childForFieldName("type_patterns");
        if (typePatternsNode) {
            for (var _i = 0, _a = typePatternsNode.children; _i < _a.length; _i++) {
                var pattern = _a[_i];
                if (pattern.type === "qualified") {
                    var qualifiedInfo = this.extractQualifiedInfo(pattern, srcBytes);
                    typePatterns.push(qualifiedInfo);
                }
                else {
                    var patternText = srcBytes
                        .slice(pattern.startIndex, pattern.endIndex)
                        .toString();
                    typePatterns.push({
                        name: patternText,
                        type: "simple",
                        context: "type_pattern",
                    });
                }
            }
        }
        var typeDefinition = "";
        var valueNode = typeInstanceNode.childForFieldName("value");
        if (valueNode) {
            if (valueNode.type === "qualified") {
                typeDefinition = this.extractQualifiedInfo(valueNode, srcBytes);
            }
            else {
                typeDefinition = {
                    name: srcBytes.slice(valueNode.startIndex, valueNode.endIndex).toString(),
                    type: "simple",
                    context: "type_definition",
                };
            }
        }
        return {
            kind: "type_instance",
            name: typeName,
            typePatterns: typePatterns,
            typeDefinition: typeDefinition,
        };
    };
    HaskellComponentExtractor.prototype.extractFunctionCalls = function (funcCode, importMap, currentModule) {
        return [];
    };
    HaskellComponentExtractor.prototype.findTypeDependencies = function (funcName, components) {
        for (var _i = 0, components_2 = components; _i < components_2.length; _i++) {
            var comp = components_2[_i];
            if (comp.kind === "function" && comp.name === funcName) {
                var sig = comp.typeSignature;
                if (!sig) {
                    return [];
                }
                var typePart = sig.split("::", 2)[1];
                var deps = typePart.match(/\b[A-Z][A-Za-z0-9_.]*\b/g) || [];
                return __spreadArray([], new Set(deps), true).sort();
            }
        }
        return [];
    };
    return HaskellComponentExtractor;
}());
exports.HaskellComponentExtractor = HaskellComponentExtractor;
