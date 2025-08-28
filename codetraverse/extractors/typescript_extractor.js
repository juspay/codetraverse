"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.TypeScriptComponentExtractor = void 0;
var tree_sitter_1 = require("tree-sitter");
var TypeScript = require("tree-sitter-typescript");
var fs = require("fs");
var path = require("path");
var chardet_1 = require("chardet");
var cheerio_1 = require("cheerio");
function parseHtmlToText(filePath) {
    var raw = fs.readFileSync(filePath);
    var guess = (0, chardet_1.detect)(raw);
    var encoding = guess || 'utf-8';
    var text = new TextDecoder(encoding).decode(raw);
    var $ = (0, cheerio_1.load)(text);
    return $.root().text();
}
function findTsconfigDir(rootDir, filePath, configFilename) {
    if (configFilename === void 0) { configFilename = "tsconfig.json"; }
    var currentDir = path.resolve(path.dirname(filePath));
    var resolvedRootDir = path.resolve(rootDir);
    while (true) {
        var candidate = path.join(currentDir, configFilename);
        if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
            return currentDir;
        }
        var parent_1 = path.dirname(currentDir);
        if (currentDir === resolvedRootDir || parent_1 === currentDir) {
            return null;
        }
        currentDir = parent_1;
    }
}
function stripJsonComments(text) {
    return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*/g, '');
}
function pathsAliasesFromTsconfig(configFilePath) {
    var _a;
    if (!fs.existsSync(configFilePath) || !fs.statSync(configFilePath).isFile()) {
        return {};
    }
    try {
        var raw = fs.readFileSync(configFilePath, 'utf-8');
        var clean = stripJsonComments(raw).trim();
        if (!clean) {
            return {};
        }
        var cfg = JSON.parse(clean);
        var paths = ((_a = cfg.compilerOptions) === null || _a === void 0 ? void 0 : _a.paths) || {};
        if (typeof paths === 'object' && paths !== null) {
            return paths;
        }
        return {};
    }
    catch (e) {
        return {};
    }
}
function resolveCalleeId(calleeId, configDir, aliasPaths) {
    var _a = calleeId.includes("::") ? calleeId.split("::", 2) : [calleeId, null], importPath = _a[0], method = _a[1];
    var sortedAliases = Object.entries(aliasPaths).sort(function (a, b) {
        var aStars = (a[0].match(/\*/g) || []).length;
        var bStars = (b[0].match(/\*/g) || []).length;
        if (aStars !== bStars) {
            return aStars - bStars;
        }
        return b[0].length - a[0].length;
    });
    for (var _i = 0, sortedAliases_1 = sortedAliases; _i < sortedAliases_1.length; _i++) {
        var _b = sortedAliases_1[_i], aliasPattern = _b[0], targets = _b[1];
        if (aliasPattern.includes("*")) {
            var regex = new RegExp("^" + aliasPattern.replace(/\*/g, "(.+)") + "$");
            var m = importPath.match(regex);
            if (!m) {
                continue;
            }
            var wildcards = m.slice(1);
            for (var _c = 0, targets_1 = targets; _c < targets_1.length; _c++) {
                var tpl = targets_1[_c];
                var rel = tpl;
                for (var _d = 0, wildcards_1 = wildcards; _d < wildcards_1.length; _d++) {
                    var w = wildcards_1[_d];
                    rel = rel.replace("*", w);
                }
                var absPath = path.normalize(path.join(configDir, rel));
                return method ? "".concat(absPath, "::").concat(method) : absPath;
            }
        }
        else {
            if (importPath === aliasPattern) {
                for (var _e = 0, targets_2 = targets; _e < targets_2.length; _e++) {
                    var tpl = targets_2[_e];
                    var absPath = path.normalize(path.join(configDir, tpl));
                    return method ? "".concat(absPath, "::").concat(method) : absPath;
                }
            }
        }
    }
    return calleeId;
}
var TypeScriptComponentExtractor = /** @class */ (function () {
    function TypeScriptComponentExtractor() {
        this.allComponents = [];
        this.parser = new tree_sitter_1.default();
        this.tsLanguage = TypeScript.typescript;
        this.parser.setLanguage(this.tsLanguage);
    }
    TypeScriptComponentExtractor.prototype.processFile = function (filePath) {
        try {
            var code = fs.readFileSync(filePath, 'utf-8');
            var tree = this.parser.parse(code);
            var rootFolder = path.dirname(filePath);
            var imports = this.collectImportsForFile(tree.rootNode, code);
            var components = this.walkNode(tree.rootNode, code, filePath, rootFolder, undefined, imports);
            for (var _i = 0, components_1 = components; _i < components_1.length; _i++) {
                var comp = components_1[_i];
                var rootDir = process.env.ROOT_DIR || "";
                if (rootDir && filePath) {
                    comp.file_path = path.relative(rootDir, filePath).replace(/\\/g, "/");
                }
                else {
                    comp.file_path = filePath.replace(/\\/g, "/");
                }
                if (!comp.module || comp.file_path.split(".").length === 2) {
                    comp.module = comp.file_path;
                }
            }
            this.allComponents = components.filter(function (c) {
                try {
                    JSON.stringify(c);
                    return true;
                }
                catch (e) {
                    return false;
                }
            });
        }
        catch (e) {
            console.error("Failed to process file: ".concat(filePath));
            console.error(e);
            this.allComponents = [];
        }
    };
    TypeScriptComponentExtractor.prototype.writeToFile = function (outputPath) {
        var serializable = this.allComponents.filter(function (comp) {
            try {
                JSON.stringify(comp);
                return true;
            }
            catch (e) {
                console.error("Skipping non-serializable component: ".concat(e));
                return false;
            }
        });
        fs.writeFileSync(outputPath, JSON.stringify(serializable, null, 2), "utf-8");
    };
    TypeScriptComponentExtractor.prototype.extractAllComponents = function () {
        return this.allComponents;
    };
    TypeScriptComponentExtractor.prototype.getText = function (node, code) {
        return code.substring(node.startIndex, node.endIndex);
    };
    TypeScriptComponentExtractor.prototype.getRelativePath = function (filePath, rootFolder) {
        var relPath = path.relative(rootFolder, filePath).replace(/\\/g, "/");
        return relPath.endsWith(".ts") ? relPath.slice(0, -3) : relPath;
    };
    TypeScriptComponentExtractor.prototype.resolveImports = function (node, code, currentFilePath, rootFolder) {
        var imports = {};
        if (node.type === 'import_statement') {
            var importText = this.getText(node, code);
            if (importText.includes('from')) {
                var parts = importText.split('from');
                var sourcePath = parts[1].trim().replace(/['";]/g, "");
                var absSource = path.normalize(path.join(path.dirname(currentFilePath), sourcePath + ".ts"));
                var relativeImportPath = this.getRelativePath(absSource, rootFolder);
                if (importText.includes('{')) {
                    var names = importText.split('{')[1].split('}')[0].split(',');
                    for (var _i = 0, names_1 = names; _i < names_1.length; _i++) {
                        var name_1 = names_1[_i];
                        name_1 = name_1.trim();
                        if (name_1.includes(' as ')) {
                            var _a = name_1.split(' as ').map(function (s) { return s.trim(); }), orig = _a[0], alias = _a[1];
                            imports[alias] = relativeImportPath;
                        }
                        else {
                            imports[name_1] = relativeImportPath;
                        }
                    }
                }
            }
        }
        for (var _b = 0, _c = node.children; _b < _c.length; _b++) {
            var child = _c[_b];
            Object.assign(imports, this.resolveImports(child, code, currentFilePath, rootFolder));
        }
        return imports;
    };
    TypeScriptComponentExtractor.prototype.parseFile = function (filePath) {
        var plain = parseHtmlToText(filePath);
        var tree = this.parser.parse(plain);
        return [plain, tree];
    };
    TypeScriptComponentExtractor.prototype.extractIdent = function (node, code) {
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (['identifier', 'type_identifier', 'property_identifier'].includes(c.type)) {
                return this.getText(c, code);
            }
        }
        return null;
    };
    TypeScriptComponentExtractor.prototype.parseImports = function (node, code) {
        var imports = {};
        if (node.type === 'import_statement') {
            var text = this.getText(node, code);
            if (text.includes('from')) {
                var parts = text.split('from');
                var left = parts[0];
                var right = parts[1].trim().replace(/['";]/g, "");
                if (left.includes('{')) {
                    var names = left.split('{')[1].split('}')[0].split(',');
                    for (var _i = 0, names_2 = names; _i < names_2.length; _i++) {
                        var n = names_2[_i];
                        n = n.trim();
                        if (n.includes(' as ')) {
                            var _a = n.split(' as ').map(function (x) { return x.trim(); }), orig = _a[0], alias = _a[1];
                            imports[alias] = right;
                        }
                        else {
                            imports[n] = right;
                        }
                    }
                }
            }
        }
        for (var _b = 0, _c = node.children; _b < _c.length; _b++) {
            var c = _c[_b];
            Object.assign(imports, this.parseImports(c, code));
        }
        return imports;
    };
    TypeScriptComponentExtractor.prototype.collectImportsForFile = function (rootNode, code) {
        var imports = {};
        for (var _i = 0, _a = rootNode.children; _i < _a.length; _i++) {
            var child = _a[_i];
            if (child.type === 'import_statement') {
                Object.assign(imports, this.parseImports(child, code));
            }
        }
        return imports;
    };
    TypeScriptComponentExtractor.prototype.extractTypeAnnotation = function (node, code) {
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === 'type_annotation' || c.type === 'type') {
                return this.getText(c, code);
            }
        }
        return null;
    };
    TypeScriptComponentExtractor.prototype.extractEnumMembers = function (node, code) {
        var members = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === "enum_body") {
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var cc = _c[_b];
                    if (["enum_assignment", "property_identifier", "identifier"].includes(cc.type)) {
                        var memberName = null;
                        var memberValue = null;
                        for (var _d = 0, _e = cc.children; _d < _e.length; _d++) {
                            var sub = _e[_d];
                            if (["property_identifier", "identifier"].includes(sub.type)) {
                                memberName = this.getText(sub, code);
                            }
                            else if (!["=", ":"].includes(sub.type)) {
                                memberValue = this.getText(sub, code);
                            }
                        }
                        if (memberName) {
                            members.push({ name: memberName, value: memberValue });
                        }
                    }
                }
            }
        }
        return members;
    };
    TypeScriptComponentExtractor.prototype.extractModifiers = function (node) {
        var mods = { "static": false, "abstract": false, "readonly": false, "override": false };
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type in mods) {
                mods[c.type] = true;
            }
        }
        return mods;
    };
    TypeScriptComponentExtractor.prototype.extractTypeStructure = function (node, code) {
        if (["type_identifier", "predefined_type"].includes(node.type)) {
            return this.getText(node, code);
        }
        if (node.type === "object_type") {
            var props = {};
            for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
                var child = _a[_i];
                if (child.type === "property_signature") {
                    var key = null;
                    var value = null;
                    for (var _b = 0, _c = child.children; _b < _c.length; _b++) {
                        var n = _c[_b];
                        if (n.type === "property_identifier") {
                            key = this.getText(n, code);
                        }
                        else if (n.type === "type_annotation" && n.children.length > 1) {
                            value = this.extractTypeStructure(n.children[1], code);
                        }
                    }
                    if (key) {
                        props[key] = value;
                    }
                }
            }
            return { "object_type": props };
        }
        if (node.type === "array_type") {
            for (var _d = 0, _e = node.children; _d < _e.length; _d++) {
                var c = _e[_d];
                if (["type_identifier", "predefined_type", "object_type"].includes(c.type)) {
                    return [this.extractTypeStructure(c, code)];
                }
            }
        }
        return this.getText(node, code);
    };
    TypeScriptComponentExtractor.prototype.extractTypeParamsStructured = function (node, code) {
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === 'type_parameters') {
                var params = [];
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var param = _c[_b];
                    if (param.type === "type_parameter") {
                        var name_2 = null;
                        var constraint = null;
                        var defaultType = null;
                        for (var _d = 0, _e = param.children; _d < _e.length; _d++) {
                            var child = _e[_d];
                            if (child.type === "type_identifier") {
                                name_2 = this.getText(child, code);
                            }
                            else if (child.type === "constraint" && child.children.length > 1) {
                                constraint = this.extractTypeStructure(child.children[1], code);
                            }
                            else if (child.type === "default_type" && child.children.length > 1) {
                                defaultType = this.extractTypeStructure(child.children[1], code);
                            }
                        }
                        params.push({
                            name: name_2,
                            constraint: constraint,
                            default: defaultType,
                        });
                    }
                }
                return params;
            }
        }
        return [];
    };
    TypeScriptComponentExtractor.prototype.extractTypeParamConstraints = function (node, code) {
        var constraints = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === "type_parameters") {
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var param = _c[_b];
                    if (param.type === "type_parameter") {
                        for (var _d = 0, _e = param.children; _d < _e.length; _d++) {
                            var child = _e[_d];
                            if (child.type === "constraint") {
                                constraints.push(this.getText(child, code));
                            }
                        }
                    }
                }
            }
        }
        return constraints;
    };
    TypeScriptComponentExtractor.prototype.extractGenericTypeDependencies = function (node, code) {
        var deps = [];
        var name = null;
        var typeArgs = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === "type_identifier") {
                name = this.getText(c, code);
            }
            else if (c.type === "type_arguments") {
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var arg = _c[_b];
                    if (arg.type !== ",") {
                        typeArgs.push(this.getText(arg, code));
                    }
                }
            }
        }
        if (name) {
            deps.push(name);
        }
        deps.push.apply(deps, typeArgs);
        return deps;
    };
    TypeScriptComponentExtractor.prototype.extractLookupTypeDependencies = function (node, code) {
        var deps = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (["type_identifier", "literal_type"].includes(c.type)) {
                deps.push(this.getText(c, code));
            }
            else if (c.type === "lookup_type") {
                deps.push.apply(deps, this.extractLookupTypeDependencies(c, code));
            }
        }
        return deps;
    };
    TypeScriptComponentExtractor.prototype.extractConditionalTypeDependencies = function (node, code) {
        var deps = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (["type_identifier", "predefined_type", "literal_type"].includes(c.type)) {
                deps.push(this.getText(c, code));
            }
            else if (["consequence", "alternative", "left", "right"].includes(c.type)) {
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var cc = _c[_b];
                    if (["type_identifier", "predefined_type", "literal_type"].includes(cc.type)) {
                        deps.push(this.getText(cc, code));
                    }
                }
            }
        }
        return deps;
    };
    TypeScriptComponentExtractor.prototype.extractMappedTypeDependencies = function (node, code) {
        var deps = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === "type_identifier") {
                deps.push(this.getText(c, code));
            }
            else if (c.type === "index_type_query") {
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var cc = _c[_b];
                    if (cc.type === "type_identifier") {
                        deps.push(this.getText(cc, code));
                    }
                }
            }
        }
        return deps;
    };
    TypeScriptComponentExtractor.prototype.extractIndexSignatures = function (node, code) {
        var indices = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === "index_signature") {
                indices.push(this.getText(c, code));
            }
        }
        return indices;
    };
    TypeScriptComponentExtractor.prototype.extractDecorators = function (node, code) {
        var decorators = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === 'decorator') {
                decorators.push(this.getText(c, code));
            }
        }
        return decorators;
    };
    TypeScriptComponentExtractor.prototype.extractParameters = function (node, code) {
        var params = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === 'formal_parameters') {
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var param = _c[_b];
                    if (['required_parameter', 'optional_parameter'].includes(param.type)) {
                        var name_3 = null;
                        var type = null;
                        var defaultValue = null;
                        for (var _d = 0, _e = param.children; _d < _e.length; _d++) {
                            var pc = _e[_d];
                            if (['identifier', 'pattern', 'type_identifier'].includes(pc.type)) {
                                name_3 = this.getText(pc, code);
                            }
                            if (pc.type === 'type_annotation') {
                                type = this.getText(pc, code);
                            }
                            if (pc.type === '_initializer') {
                                defaultValue = this.getText(pc, code);
                            }
                        }
                        params.push({
                            name: name_3,
                            type: type,
                            default: defaultValue,
                        });
                    }
                }
            }
        }
        return params;
    };
    TypeScriptComponentExtractor.prototype.extractTypeParams = function (node, code) {
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === 'type_parameters' || c.type === 'formal_type_parameters') {
                return this.getText(c, code);
            }
        }
        return null;
    };
    TypeScriptComponentExtractor.prototype.extractExtendsImplements = function (node, code) {
        var bases = [];
        var impls = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === 'class_heritage') {
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var cc = _c[_b];
                    if (cc.type === 'extends_clause') {
                        for (var _d = 0, _e = cc.children; _d < _e.length; _d++) {
                            var base = _e[_d];
                            if (base.fieldName === "value") {
                                var baseName = this.getText(base, code);
                                if (baseName) {
                                    bases.push(baseName);
                                }
                            }
                            else if (['identifier', 'type_identifier'].includes(base.type)) {
                                var baseName = this.getText(base, code);
                                if (baseName) {
                                    bases.push(baseName);
                                }
                            }
                        }
                    }
                    if (cc.type === 'implements_clause') {
                        for (var _f = 0, _g = cc.children; _f < _g.length; _f++) {
                            var iface = _g[_f];
                            if (iface.type === 'type') {
                                var ifaceName = this.getText(iface, code);
                                if (ifaceName) {
                                    impls.push(ifaceName);
                                }
                            }
                            else if (['identifier', 'type_identifier'].includes(iface.type)) {
                                var ifaceName = this.getText(iface, code);
                                if (ifaceName) {
                                    impls.push(ifaceName);
                                }
                            }
                        }
                    }
                }
            }
        }
        return [bases, impls];
    };
    TypeScriptComponentExtractor.prototype.extractInterfaceExtends = function (node, code) {
        var parents = [];
        for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
            var c = _a[_i];
            if (c.type === 'extends_type_clause') {
                for (var _b = 0, _c = c.children; _b < _c.length; _b++) {
                    var cc = _c[_b];
                    if (cc.type === 'type') {
                        var parentName = this.getText(cc, code);
                        if (parentName) {
                            parents.push(parentName);
                        }
                    }
                }
            }
        }
        return parents;
    };
    TypeScriptComponentExtractor.prototype.extractExpressionStatementCalls = function (node, code, moduleName, filePath) {
        var results = [];
        if (node.type === "expression_statement") {
            var expr = node.children[0];
            if (expr && expr.type === "call_expression") {
                var fn = expr.childForFieldName("function");
                if (fn && fn.type === "member_expression") {
                    var objectNode = fn.childForFieldName("object");
                    var propertyNode = fn.childForFieldName("property");
                    if (objectNode && propertyNode) {
                        var objectName = this.getText(objectNode, code);
                        var propertyName = this.getText(propertyNode, code);
                        var jsdoc = this.extractJsdoc(node, code);
                        var argNodes = expr.childForFieldName("arguments");
                        var args = [];
                        if (argNodes) {
                            for (var _i = 0, _a = argNodes.children; _i < _a.length; _i++) {
                                var arg = _a[_i];
                                if (arg.type !== ',') {
                                    args.push(this.getText(arg, code));
                                }
                            }
                        }
                        results.push({
                            kind: "function_call",
                            module: moduleName,
                            object: objectName,
                            method: propertyName,
                            arguments: args,
                            start_line: node.startPosition.row + 1,
                            end_line: node.endPosition.row + 1,
                            jsdoc: jsdoc,
                        });
                    }
                }
            }
        }
        return results;
    };
    TypeScriptComponentExtractor.prototype.extractFunctionCalls = function (filePath, node, code, moduleName, imports, className, classBases) {
        var _this = this;
        var calls = [];
        var visit = function (n) {
            if (n.type === 'call_expression') {
                var fn = n.childForFieldName('function');
                if (!fn) {
                    return;
                }
                if (fn.type === "member_expression") {
                    var objectNode = fn.childForFieldName("object");
                    var propertyNode = fn.childForFieldName("property");
                    var methodName = propertyNode ? _this.getText(propertyNode, code) : null;
                    if (objectNode) {
                        if (objectNode.type === "super") {
                            var baseClass = classBases && classBases.length > 0 ? classBases[0] : "(super_class)";
                            var calleeId = "".concat(moduleName, "::").concat(baseClass, ".").concat(methodName);
                            calls.push({
                                name: "super.".concat(methodName),
                                base_name: methodName,
                                resolved_callee: calleeId,
                            });
                        }
                        else if (objectNode.type === "this") {
                            var calleeId = "".concat(moduleName, "::").concat(className || "(this_class)", ".").concat(methodName);
                            calls.push({
                                name: "this.".concat(methodName),
                                base_name: methodName,
                                resolved_callee: calleeId,
                            });
                        }
                        else if (objectNode.type === "identifier") {
                            var objName = _this.getText(objectNode, code);
                            var calleeId = "".concat(moduleName, "::").concat(objName, ".").concat(methodName);
                            calls.push({
                                name: "".concat(objName, ".").concat(methodName),
                                base_name: methodName,
                                resolved_callee: calleeId,
                            });
                        }
                    }
                }
                else if (fn.type === "identifier") {
                    var calleeText = _this.getText(fn, code);
                    var baseName = calleeText;
                    var calleeId = void 0;
                    if (baseName in imports) {
                        var sourceFile = imports[baseName];
                        if (typeof sourceFile === 'string' && !sourceFile.endsWith('.ts')) {
                            sourceFile += '.ts';
                        }
                        calleeId = "".concat(sourceFile, "::").concat(baseName);
                    }
                    else {
                        calleeId = "".concat(filePath, "::").concat(baseName);
                    }
                    if (calleeId.startsWith("./")) {
                        calls.push({
                            name: calleeText,
                            base_name: baseName,
                            resolved_callee: calleeId,
                        });
                    }
                    else {
                        var rootDir = process.env.ROOT_DIR || "";
                        var configDir = findTsconfigDir(rootDir, filePath);
                        var absoluteCalleeId = void 0;
                        if (configDir) {
                            var completeConfigPath = path.join(configDir, "tsconfig.json");
                            var aliasPaths = pathsAliasesFromTsconfig(completeConfigPath);
                            absoluteCalleeId = resolveCalleeId(calleeId, configDir, aliasPaths);
                            if (absoluteCalleeId.startsWith(configDir)) {
                                absoluteCalleeId = path.relative(rootDir, absoluteCalleeId);
                            }
                        }
                        else {
                            console.log("typescript issue No tsconfig.json found up to ".concat(rootDir));
                        }
                        calls.push({
                            name: calleeText,
                            base_name: baseName,
                            resolved_callee: absoluteCalleeId || calleeId,
                        });
                    }
                }
                var args = n.childForFieldName('arguments');
                if (args) {
                    for (var _i = 0, _a = args.children; _i < _a.length; _i++) {
                        var arg = _a[_i];
                        visit(arg);
                    }
                }
            }
            for (var _b = 0, _c = n.children; _b < _c.length; _b++) {
                var c = _c[_b];
                visit(c);
            }
        };
        visit(node);
        return calls;
    };
    TypeScriptComponentExtractor.prototype.extractTypeDependencies = function (node, code) {
        var _this = this;
        var deps = new Set();
        var visit = function (n) {
            if (['type_identifier', 'predefined_type', 'nested_type_identifier', 'generic_type'].includes(n.type)) {
                deps.add(_this.getText(n, code));
            }
            else if (['union_type', 'intersection_type', 'parenthesized_type'].includes(n.type)) {
                for (var _i = 0, _a = n.children; _i < _a.length; _i++) {
                    var c = _a[_i];
                    if (!["|", "&", "(", ")"].includes(c.type)) {
                        visit(c);
                    }
                }
            }
            else {
                for (var _b = 0, _c = n.children; _b < _c.length; _b++) {
                    var c = _c[_b];
                    visit(c);
                }
            }
        };
        visit(node);
        return Array.from(deps);
    };
    TypeScriptComponentExtractor.prototype.getFullComponentPath = function (filePath, rootFolder, name, className) {
        var relPath = path.relative(rootFolder, filePath).replace(/\\/g, "/");
        if (className) {
            return "".concat(relPath, "::").concat(className, ".").concat(name);
        }
        return "".concat(relPath, "::").concat(name);
    };
    TypeScriptComponentExtractor.prototype.getRelativeModulePath = function (filePath, rootFolder) {
        return path.relative(rootFolder, filePath).replace(/\\/g, "/").replace(/^\.\//, "");
    };
    TypeScriptComponentExtractor.prototype.extractJsdoc = function (node, code) {
        var prevSibling = node.previousSibling;
        while (prevSibling) {
            if (prevSibling.type === 'comment') {
                var commentText = this.getText(prevSibling, code);
                if (commentText.trim().startsWith('/**')) {
                    return commentText;
                }
            }
            else if (prevSibling.type.trim() !== '') {
                break;
            }
            prevSibling = prevSibling.previousSibling;
        }
        return null;
    };
    TypeScriptComponentExtractor.prototype.walkNode = function (node, code, filePath, rootFolder, context, imports) {
        if (imports === void 0) { imports = {}; }
        var results = [];
        var moduleName = this.getRelativeModulePath(filePath, rootFolder);
        if (node.type === 'function_declaration' || node.type === 'function_signature') {
            var fnName = this.extractIdent(node, code);
            var typeSig = this.extractTypeAnnotation(node, code);
            var typeParams = this.extractTypeParams(node, code);
            var typeParamConstraints = this.extractTypeParamConstraints(node, code);
            var decorators = this.extractDecorators(node, code);
            var params = this.extractParameters(node, code);
            var startLine = node.startPosition.row + 1;
            var endLine = node.endPosition.row + 1;
            var body = null;
            for (var _i = 0, _a = node.children; _i < _a.length; _i++) {
                var c = _a[_i];
                if (c.type.includes("block")) {
                    body = c;
                    break;
                }
            }
            var functionCalls = body ? this.extractFunctionCalls(filePath, body, code, moduleName, imports) : [];
            var typeDeps = this.extractTypeDependencies(node, code);
            var jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "function",
                module: moduleName,
                name: fnName,
                type_signature: typeSig,
                type_parameters: typeParams,
                type_param_constraints: typeParamConstraints,
                type_parameters_structured: this.extractTypeParamsStructured(node, code),
                parameters: params,
                decorators: decorators,
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                function_calls: functionCalls,
                type_dependencies: typeDeps,
                parent: context === null || context === void 0 ? void 0 : context.parent,
                code: this.getText(node, code),
            });
        }
        if (node.type === 'class_declaration' || node.type === 'class' || node.type === 'abstract_class_declaration') {
            var className = this.extractIdent(node, code);
            var _b = this.extractExtendsImplements(node, code), bases = _b[0], impls = _b[1];
            var typeParams = this.extractTypeParams(node, code);
            var typeParamConstraints = this.extractTypeParamConstraints(node, code);
            var decorators = this.extractDecorators(node, code);
            var indexSignatures = this.extractIndexSignatures(node, code);
            var startLine = node.startPosition.row + 1;
            var endLine = node.endPosition.row + 1;
            var jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "class",
                module: moduleName,
                name: className,
                type_parameters: typeParams,
                type_param_constraints: typeParamConstraints,
                decorators: decorators,
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                bases: bases,
                implements: impls,
                index_signatures: indexSignatures,
                code: this.getText(node, code),
            });
            for (var _c = 0, _d = node.children; _c < _d.length; _c++) {
                var c = _d[_c];
                if (c.type === 'class_body') {
                    var prevDecorators = [];
                    for (var _e = 0, _f = c.children; _e < _f.length; _e++) {
                        var m = _f[_e];
                        if (m.type === 'decorator') {
                            prevDecorators.push(this.getText(m, code));
                        }
                        else if (m.type === 'method_definition') {
                            var methodName = null;
                            for (var _g = 0, _h = m.children; _g < _h.length; _g++) {
                                var child = _h[_g];
                                if (['property_identifier', 'identifier', 'type_identifier'].includes(child.type)) {
                                    methodName = this.getText(child, code);
                                    break;
                                }
                            }
                            var typeSig = this.extractTypeAnnotation(m, code);
                            var methodBody = null;
                            for (var _j = 0, _k = m.children; _j < _k.length; _j++) {
                                var child = _k[_j];
                                if (["statement_block", "body", "block"].includes(child.type)) {
                                    methodBody = child;
                                    break;
                                }
                            }
                            var mCalls = methodBody ? this.extractFunctionCalls(filePath, methodBody, code, moduleName, imports, className || undefined, bases) : [];
                            var mTypeParams = this.extractTypeParams(m, code);
                            var mParams = this.extractParameters(m, code);
                            var mDecorators = prevDecorators;
                            prevDecorators = [];
                            var mStart = m.startPosition.row + 1;
                            var mEnd = m.endPosition.row + 1;
                            var mTypeDeps = this.extractTypeDependencies(m, code);
                            var mMods = this.extractModifiers(m);
                            var isGetter = m.children.some(function (child) { return child.type === 'get'; });
                            var isSetter = m.children.some(function (child) { return child.type === 'set'; });
                            var kind = methodName === "constructor" ? "constructor" : "method";
                            var methodJsdoc = this.extractJsdoc(m, code);
                            results.push({
                                kind: kind,
                                module: moduleName,
                                name: methodName,
                                class: className,
                                type_signature: typeSig,
                                type_parameters: mTypeParams,
                                parameters: mParams,
                                decorators: mDecorators,
                                start_line: mStart,
                                end_line: mEnd,
                                jsdoc: methodJsdoc,
                                function_calls: mCalls,
                                type_dependencies: mTypeDeps,
                                parent: className,
                                static: mMods["static"],
                                abstract: mMods["abstract"],
                                readonly: mMods["readonly"],
                                override: mMods["override"],
                                getter: isGetter,
                                setter: isSetter,
                                code: this.getText(m, code),
                            });
                        }
                        else if (m.type === 'public_field_definition') {
                            var fieldName = null;
                            for (var _l = 0, _m = m.children; _l < _m.length; _l++) {
                                var child = _m[_l];
                                if (['property_identifier', 'identifier', 'type_identifier'].includes(child.type)) {
                                    fieldName = this.getText(child, code);
                                    break;
                                }
                            }
                            var typeSig = this.extractTypeAnnotation(m, code);
                            var mDecorators = prevDecorators;
                            prevDecorators = [];
                            var mStart = m.startPosition.row + 1;
                            var mEnd = m.endPosition.row + 1;
                            var mMods = this.extractModifiers(m);
                            var fieldJsdoc = this.extractJsdoc(m, code);
                            results.push({
                                kind: "field",
                                module: moduleName,
                                name: fieldName,
                                class: className,
                                type_signature: typeSig,
                                decorators: mDecorators,
                                start_line: mStart,
                                end_line: mEnd,
                                jsdoc: fieldJsdoc,
                                parent: className,
                                static: mMods["static"],
                                abstract: mMods["abstract"],
                                readonly: mMods["readonly"],
                                override: mMods["override"],
                                code: this.getText(m, code),
                            });
                        }
                    }
                }
            }
        }
        if (node.type === 'interface_declaration') {
            var interfaceName = this.extractIdent(node, code);
            var typeParams = this.extractTypeParams(node, code);
            var typeParamConstraints = this.extractTypeParamConstraints(node, code);
            var parents = this.extractInterfaceExtends(node, code);
            var indexSignatures = this.extractIndexSignatures(node, code);
            var startLine = node.startPosition.row + 1;
            var endLine = node.endPosition.row + 1;
            var typeDeps = [];
            for (var _o = 0, _p = node.children; _o < _p.length; _o++) {
                var c = _p[_o];
                if (c.type === "interface_body") {
                    for (var _q = 0, _r = c.children; _q < _r.length; _q++) {
                        var member = _r[_q];
                        if (member.type === "property_signature") {
                            for (var _s = 0, _t = member.children; _s < _t.length; _s++) {
                                var propChild = _t[_s];
                                if (propChild.type === "type_annotation") {
                                    for (var _u = 0, _v = propChild.children; _u < _v.length; _u++) {
                                        var typeAnnChild = _v[_u];
                                        if (["type_identifier", "predefined_type", "literal_type"].includes(typeAnnChild.type)) {
                                            typeDeps.push(this.getText(typeAnnChild, code));
                                        }
                                        else if (typeAnnChild.type === "generic_type") {
                                            typeDeps.push.apply(typeDeps, this.extractGenericTypeDependencies(typeAnnChild, code));
                                        }
                                        else if (typeAnnChild.type === "lookup_type") {
                                            typeDeps.push.apply(typeDeps, this.extractLookupTypeDependencies(typeAnnChild, code));
                                        }
                                        else if (typeAnnChild.type === "conditional_type") {
                                            typeDeps.push.apply(typeDeps, this.extractConditionalTypeDependencies(typeAnnChild, code));
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            typeDeps = Array.from(new Set(typeDeps));
            var jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "interface",
                module: moduleName,
                name: interfaceName,
                type_parameters: typeParams,
                type_param_constraints: typeParamConstraints,
                extends: parents,
                index_signatures: indexSignatures,
                type_dependencies: typeDeps,
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                code: this.getText(node, code),
            });
        }
        if (node.type === 'type_alias_declaration') {
            var typeName = this.extractIdent(node, code);
            var typeParams = this.extractTypeParams(node, code);
            var typeParamConstraints = this.extractTypeParamConstraints(node, code);
            var typeDeps = this.extractTypeDependencies(node, code);
            var valueNode = null;
            for (var _w = 0, _x = node.children; _w < _x.length; _w++) {
                var c = _x[_w];
                if (["generic_type", "object_type", "union_type", "lookup_type", "conditional_type"].includes(c.type)) {
                    valueNode = c;
                    break;
                }
                if (c.type === "type" && c.children.length > 0) {
                    if (["generic_type", "object_type", "union_type", "lookup_type", "conditional_type"].includes(c.children[0].type)) {
                        valueNode = c.children[0];
                        break;
                    }
                }
            }
            if (valueNode) {
                if (valueNode.type === "generic_type") {
                    typeDeps.push.apply(typeDeps, this.extractGenericTypeDependencies(valueNode, code));
                }
                else if (valueNode.type === "lookup_type") {
                    typeDeps.push.apply(typeDeps, this.extractLookupTypeDependencies(valueNode, code));
                }
                else if (valueNode.type === "conditional_type") {
                    typeDeps.push.apply(typeDeps, this.extractConditionalTypeDependencies(valueNode, code));
                }
                else if (valueNode.type === "object_type") {
                    for (var _y = 0, _z = valueNode.children; _y < _z.length; _y++) {
                        var child = _z[_y];
                        if (child.type === "index_signature") {
                            for (var _0 = 0, _1 = child.children; _0 < _1.length; _0++) {
                                var grandchild = _1[_0];
                                if (grandchild.type === "mapped_type_clause") {
                                    typeDeps.push.apply(typeDeps, this.extractMappedTypeDependencies(grandchild, code));
                                }
                                if (grandchild.type === "type_annotation") {
                                    for (var _2 = 0, _3 = grandchild.children; _2 < _3.length; _2++) {
                                        var ggc = _3[_2];
                                        if (ggc.type === "lookup_type") {
                                            typeDeps.push.apply(typeDeps, this.extractLookupTypeDependencies(ggc, code));
                                        }
                                    }
                                }
                                if (grandchild.type === "opting_type_annotation") {
                                    for (var _4 = 0, _5 = grandchild.children; _4 < _5.length; _4++) {
                                        var ggc = _5[_4];
                                        if (ggc.type === "lookup_type") {
                                            typeDeps.push.apply(typeDeps, this.extractLookupTypeDependencies(ggc, code));
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                else if (valueNode.type === "union_type") {
                    for (var _6 = 0, _7 = valueNode.children; _6 < _7.length; _6++) {
                        var child = _7[_6];
                        if (["type_identifier", "literal_type"].includes(child.type)) {
                            typeDeps.push(this.getText(child, code));
                        }
                    }
                }
            }
            var startLine = node.startPosition.row + 1;
            var endLine = node.endPosition.row + 1;
            var jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "type_alias",
                module: moduleName,
                name: typeName,
                type_parameters: typeParams,
                type_param_constraints: typeParamConstraints,
                type_dependencies: Array.from(new Set(typeDeps)),
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                code: this.getText(node, code),
            });
        }
        if (node.type === 'enum_declaration') {
            var enumName = this.extractIdent(node, code);
            var startLine = node.startPosition.row + 1;
            var endLine = node.endPosition.row + 1;
            var jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "enum",
                module: moduleName,
                name: enumName,
                start_line: startLine,
                end_line: endLine,
                jsdoc: jsdoc,
                members: this.extractEnumMembers(node, code),
                code: this.getText(node, code),
            });
        }
        if (node.type === 'import_statement') {
            var jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "import",
                module: moduleName,
                start_line: node.startPosition.row + 1,
                end_line: node.endPosition.row + 1,
                jsdoc: jsdoc,
                code: this.getText(node, code),
            });
        }
        if (node.type === 'export_statement') {
            var jsdoc = this.extractJsdoc(node, code);
            results.push({
                kind: "export",
                module: moduleName,
                start_line: node.startPosition.row + 1,
                end_line: node.endPosition.row + 1,
                jsdoc: jsdoc,
                code: this.getText(node, code),
            });
        }
        for (var _8 = 0, _9 = node.children; _8 < _9.length; _8++) {
            var c = _9[_8];
            results.push.apply(results, this.walkNode(c, code, filePath, rootFolder, context, imports));
        }
        return results;
    };
    TypeScriptComponentExtractor.UTILITY_TYPES = new Set([
        "Partial", "Required", "Readonly", "Pick", "Omit",
        "ReturnType", "Parameters", "NonNullable", "Record", "InstanceType", "Extract", "Exclude"
    ]);
    return TypeScriptComponentExtractor;
}());
exports.TypeScriptComponentExtractor = TypeScriptComponentExtractor;
