const Parser = require("tree-sitter");
const Haskell = require("tree-sitter-haskell");

type SyntaxNode = any;
import * as fs from "fs";
import { ComponentExtractor } from "../base/component_extractor";
import {
  Component,
  FunctionCall,
  WhereDefinition,
  Import,
  DataType,
  ClassComponent,
  Instance,
  TopLevelComponent,
} from "../types/types";

const TOP_LEVEL_KINDS = new Set([
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

export class HaskellComponentExtractor implements ComponentExtractor {
  private parser: any;
  private readonly hsLanguage: any;
  private importMap: Record<string, string[]> = {};
  public allComponents: Component[] = [];
  private currentModule = "";
  private currentFilePath = "";

  constructor() {
    this.parser = new Parser();
    this.hsLanguage = Haskell;
    this.parser.setLanguage(this.hsLanguage);
  }

  processFile(filePath: string): void {
    // Read file with explicit UTF-8 encoding
    const fileContent = fs.readFileSync(filePath, "utf-8");
    this.currentFilePath = filePath;

    // Check if file is empty or contains only whitespace
    if (fileContent.trim().length === 0) {
      console.log(`Skipping empty file: ${filePath}`);
      return;
    }

    // Validate that the content can be parsed
    let tree;
    try {
      tree = this.parser.parse(fileContent);
    } catch (error) {
      // console.error(`Failed to parse file ${filePath}:`, error);
      return;
    }

    if (!tree || !tree.rootNode) {
      console.error(`Invalid parse tree for file ${filePath}`);
      return;
    }
    this.importMap = this.parseImports(tree.rootNode, Buffer.from(fileContent));

    for (const child of tree.rootNode.children) {
      if (child.type === "header") {
        const modulePath: string[] = [];
        const moduleNode = child.childForFieldName("module");
        if (moduleNode) {
          for (const moduleId of moduleNode.children) {
            if (moduleId.type === "module_id") {
              modulePath.push(
                Buffer.from(fileContent).slice(moduleId.startIndex, moduleId.endIndex).toString()
              );
            }
          }
        }
        this.currentModule = modulePath.join(".");
        break;
      }
    }

    const rawGroups = tree.rootNode.children.map((i) =>
      this.extractTopLevelComponents(i, Buffer.from(fileContent), this.importMap)
    );
    this.allComponents = rawGroups.flat();

    for (const comp of this.allComponents) {
      comp.filePath = this.currentFilePath;
    }

    for (const comp of this.allComponents) {
      if (comp.kind === "function") {
        comp.typeDependencies = this.findTypeDependencies(
          comp.name,
          this.allComponents
        );
      }
    }
  }

  writeToFile(outputPath: string): void {
    fs.writeFileSync(
      outputPath,
      JSON.stringify(this.allComponents, null, 2),
      "utf-8"
    );
  }

  extractAllComponents(): Component[] {
    return this.allComponents;
  }

  private parseImports(
    rootNode: SyntaxNode,
    srcBytes: Buffer
  ): Record<string, string[]> {
    const importMap: Record<string, string[]> = {};

    function traverse(node: SyntaxNode) {
      if (node.type === "import") {
        const moduleNode = node.childForFieldName("module");
        if (moduleNode) {
          const module = srcBytes
            .slice(moduleNode.startIndex, moduleNode.endIndex)
            .toString();
          const aliasNode = node.childForFieldName("alias");
          let alias = module.split(".").pop()!;
          if (aliasNode) {
            alias = srcBytes
              .slice(aliasNode.startIndex, aliasNode.endIndex)
              .toString();
          }
          if (!importMap[alias]) {
            importMap[alias] = [];
          }
          importMap[alias].push(module);
        }
      }
      for (const child of node.children) {
        traverse(child);
      }
    }

    traverse(rootNode);
    return importMap;
  }

  private extractTopLevelComponents(
    rootNode: SyntaxNode,
    srcBytes: Buffer,
    importMap: Record<string, string[]>
  ): TopLevelComponent[] {
    const sigs: Record<string, string> = {};
    for (const child of rootNode.children) {
      if (child.type === "signature") {
        const start = child.startPosition.row;
        const end = child.endPosition.row;
        const sigCode = srcBytes
          .toString()
          .split("\n")
          .slice(start, end + 1)
          .join("\n");
        const nameNode = child.childForFieldName("name");
        if (nameNode) {
          const name = srcBytes
            .slice(nameNode.startIndex, nameNode.endIndex)
            .toString();
          sigs[name] = sigCode;
        }
      }
    }

    const components: TopLevelComponent[] = [];

    if (rootNode.type === "header") {
      const start = rootNode.startPosition.row;
      const end = rootNode.endPosition.row;
      const headerCode = srcBytes
        .toString()
        .split("\n")
        .slice(start, end + 1)
        .join("\n");

      const modulePath: string[] = [];
      const modN = rootNode.childForFieldName("module");
      if (modN) {
        for (const mid of modN.namedChildren) {
          if (mid.type === "module_id") {
            modulePath.push(
              srcBytes.slice(mid.startIndex, mid.endIndex).toString()
            );
          }
        }
      }

      const exports: string[] = [];
      const expN = rootNode.childForFieldName("exports");
      if (expN) {
        for (const item of expN.namedChildren) {
          if (item.type === "module_export") {
            const alias = item.childForFieldName("module");
            if (alias) {
              exports.push(
                srcBytes.slice(alias.startIndex, alias.endIndex).toString()
              );
            }
          } else if (
            ["export", "import_name", "name"].includes(item.type)
          ) {
            const txt = srcBytes
              .slice(item.startIndex, item.endIndex)
              .toString()
              .trim();
            exports.push(txt);
          }
        }
      }

      if (exports.length === 0) {
        const parent = rootNode.parent;
        if (parent) {
          for (const sib of parent.children) {
            for (const child of sib.children) {
              if (child.id === rootNode.id) continue;
              if (
                [
                  "function",
                  "data_type",
                  "instance",
                  "class",
                  "newtype",
                  "type_synonym",
                ].includes(child.type)
              ) {
                const nameN =
                  child.childForFieldName("name") ||
                  child.childForFieldName("variable");
                if (nameN) {
                  exports.push(
                    srcBytes.slice(nameN.startIndex, nameN.endIndex).toString()
                  );
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
        exports: exports,
      });
      return components;
    }

    const reexportedModules: Record<string, string[]> = {};

    for (const child of rootNode.children) {
      if (child.type === "type_synonym") {
        const name = child.children[1].text;
        const code = child.text;
        components.push({
          kind: "type_synonym",
          name: name,
          code: code,
          startLine: child.startPosition.row + 1,
          endLine: child.endPosition.row + 1,
          module: this.currentModule,
        });
      } else if (child.type === "bind") {
        const code = child.text;
        const name = child.children[0].text;
        if (name) {
            components.push({
              kind: sigs[name]?.includes("->") ? "function" : "file_global_variable",
              name: name,
              code: code,
              startLine: child.startPosition.row + 1,
              endLine: child.endPosition.row + 1,
              module: this.currentModule,
              typeSignature: sigs[name] || null,
              functionCalls: this.extractFunctionCallsNode(
                child,
                srcBytes,
                importMap,
                this.currentModule
              ),
            });
        }
      } else if (child.type === "header") {
        console.log("Skipping header node in top-level extraction");
        const start = child.startPosition.row;
        const end = child.endPosition.row;
        const headerCode = srcBytes
          .toString()
          .split("\n")
          .slice(start, end + 1)
          .join("\n");
        const modulePath: string[] = [];
        const moduleNode = child.childForFieldName("module");
        if (moduleNode) {
          for (const moduleId of moduleNode.children) {
            if (moduleId.type === "module_id") {
              modulePath.push(
                srcBytes
                  .slice(moduleId.startIndex, moduleId.endIndex)
                  .toString()
              );
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
      } else if (child.type === "pragma") {
        const start = child.startPosition.row;
        const end = child.endPosition.row;
        const pragmaCode = srcBytes
          .toString()
          .split("\n")
          .slice(start, end + 1)
          .join("\n");
        const pragmaContent = pragmaCode
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
      } else if (child.type === "imports") {
        for (const importNode of child.children) {
          if (importNode.type === "import") {
            const comp = this.extractImportComponent(importNode, srcBytes);
            if (comp) {
              components.push(comp);
            }
          }
        }
      } else if (child.type === "import") {
        const comp = this.extractImportComponent(child, srcBytes);
        if (comp) {
          components.push(comp);
        }
      } else if (child.type === "class") {
        const classComp = this.extractClassComponent(child, srcBytes, importMap);
        if (classComp) {
          classComp.module = this.currentModule;
          components.push(classComp);
        }
      } else if (child.type === "function") {
        const nameNode = child.childForFieldName("name");
        const fnName = nameNode
          ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
          : "unknown";

        const bodyNode = child.childForFieldName("match");
        const bodyCode = bodyNode
          ? srcBytes.slice(bodyNode.startIndex, bodyNode.endIndex).toString()
          : "";

        const start = child.startPosition.row;
        const end = child.endPosition.row;
        const entireFuncCode = srcBytes
          .toString()
          .split("\n")
          .slice(start, end + 1)
          .join("\n");

        const comp: any = {
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
          comp.functionCalls = this.extractFunctionCallsNode(
            bodyNode,
            srcBytes,
            importMap,
            this.currentModule
          );
        } else {
          comp.functionCalls = [];
        }

        const whereDefs = this.extractWhereDefinitions(child, srcBytes);
        if (whereDefs.length > 0) {
          comp.whereDefinitions = whereDefs;
          for (const whereDef of whereDefs) {
            if (whereDef.kind === "function") {
              whereDef.functionCalls = this.extractFunctionCallsNode(
                child,
                srcBytes,
                importMap,
                this.currentModule
              );
            }
          }
        }

        components.push(comp);
        comp.reexportedFrom = reexportedModules[this.currentModule] || [];
      } else if (child.type === "instance") {
        const instanceComp = this.extractInstanceComponent(
          child,
          srcBytes,
          importMap
        );
        if (instanceComp) {
          instanceComp.module = this.currentModule;
          instanceComp.functionCalls = this.extractFunctionCallsNode(
            child,
            srcBytes,
            importMap,
            this.currentModule
          );
          components.push(instanceComp);
        }
      } else if (child.type === "data_type") {
        const dataComp = this.extractDataTypeComponent(
          child,
          srcBytes,
          importMap
        );
        if (dataComp) {
          dataComp.module = this.currentModule;
          dataComp.functionCalls = this.extractFunctionCallsNode(
            child,
            srcBytes,
            importMap,
            this.currentModule
          );
          components.push(dataComp);
        }
      }
    }

    for (const comp of components) {
      if (comp.kind === "import" && comp.alias && comp.module) {
        if (!reexportedModules[comp.module]) {
          reexportedModules[comp.module] = [];
        }
        reexportedModules[comp.module].push(comp.alias);
      }
    }

    return components;
  }

  private extractClassComponent(
    classNode: SyntaxNode,
    srcBytes: Buffer,
    importMap: Record<string, string[]>
  ): ClassComponent | null {
    const start = classNode.startPosition.row;
    const end = classNode.endPosition.row;
    const classCode = srcBytes
      .toString()
      .split("\n")
      .slice(start, end + 1)
      .join("\n");

    const nameNode = classNode.childForFieldName("name");
    const className = nameNode
      ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
      : "UnknownClass";

    const typeParams: string[] = [];
    const patternsNode = classNode.childForFieldName("patterns");
    if (patternsNode) {
      for (const paramNode of patternsNode.children) {
        if (paramNode.type === "variable") {
          const paramName = srcBytes
            .slice(paramNode.startIndex, paramNode.endIndex)
            .toString();
          typeParams.push(paramName);
        }
      }
    }

    const declarations: any[] = [];
    const declarationsNode = classNode.childForFieldName("declarations");
    if (declarationsNode) {
      for (const declNode of declarationsNode.children) {
        if (declNode.type === "declaration") {
          for (const innerDecl of declNode.children) {
            const declInfo = this.extractClassDeclaration(innerDecl, srcBytes);
            if (declInfo) {
              declarations.push(declInfo);
            }
          }
        } else {
          const declInfo = this.extractClassDeclaration(declNode, srcBytes);
          if (declInfo) {
            declarations.push(declInfo);
          }
        }
      }
    }

    let constraints: string[] = [];
    for (const child of classNode.children) {
      if (child.type === "context") {
        constraints = this.extractClassConstraints(child, srcBytes);
      }
    }

    const typeFamilies = declarations.filter(
      (d) => d.declarationType === "type_family"
    );
    const methodSigs = declarations.filter(
      (d) => d.declarationType === "method_signature"
    );
    const defaultMethods = declarations.filter(
      (d) => d.declarationType === "default_method"
    );

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
  }

  private extractClassDeclaration(
    declNode: SyntaxNode,
    srcBytes: Buffer
  ): any {
    const declStart = declNode.startPosition.row;
    const declEnd = declNode.endPosition.row;
    const declCode = srcBytes
      .toString()
      .split("\n")
      .slice(declStart, declEnd + 1)
      .join("\n");

    if (declNode.type === "type_family") {
      const nameNode = declNode.childForFieldName("name");
      const familyName = nameNode
        ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
        : "UnknownTypeFamily";

      const familyParams: string[] = [];
      const patternsNode = declNode.childForFieldName("patterns");
      if (patternsNode) {
        for (const paramNode of patternsNode.children) {
          if (paramNode.type === "variable") {
            const paramName = srcBytes
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
    } else if (declNode.type === "signature") {
      const nameNode = declNode.childForFieldName("name");
      const methodName = nameNode
        ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
        : "UnknownMethod";

      const typeNode = declNode.childForFieldName("type");
      const typeSig = typeNode
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
    } else if (declNode.type === "function") {
      const nameNode = declNode.childForFieldName("name");
      const methodName = nameNode
        ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
        : "UnknownMethod";

      return {
        declarationType: "default_method",
        name: methodName,
        code: declCode.trim(),
        startLine: declStart + 1,
        endLine: declEnd + 1,
      };
    } else {
      return {
        declarationType: declNode.type,
        code: declCode.trim(),
        startLine: declStart + 1,
        endLine: declEnd + 1,
      };
    }
  }

  private extractClassConstraints(
    contextNode: SyntaxNode,
    srcBytes: Buffer
  ): string[] {
    const constraints: string[] = [];
    for (const child of contextNode.children) {
      if (child.type === "constraint") {
        const constraintText = srcBytes
          .slice(child.startIndex, child.endIndex)
          .toString();
        constraints.push(constraintText);
      }
    }
    return constraints;
  }

  private extractFunctionCallsNode(
    functionNode: SyntaxNode,
    srcBytes: Buffer,
    importMap: Record<string, string[]>,
    currentModule: string
  ): FunctionCall[] {
    const identifiers: FunctionCall[] = [];
    const currentFileFunctions = new Set(
      this.allComponents
        .filter((c) => c.kind === "function")
        .map((c) => c.name)
    );

    const traverseNode = (node: SyntaxNode) => {
      if (node.type === "qualified") {
        const moduleNode = node.childForFieldName("module");
        const idNode =
          node.childForFieldName("id") || node.childForFieldName("variable");

        if (moduleNode && idNode) {
          const moduleParts: string[] = [];
          for (const child of moduleNode.children) {
            if (child.type === "module_id") {
              moduleParts.push(
                srcBytes.slice(child.startIndex, child.endIndex).toString()
              );
            }
          }

          const prefix = moduleParts.join(".");
          const baseName = srcBytes
            .slice(idNode.startIndex, idNode.endIndex)
            .toString();

          let resolvedModules = [prefix];
          if (moduleParts.length > 0) {
            const firstComponent = moduleParts[0];
            if (importMap[firstComponent]) {
              let resolved = importMap[firstComponent];
              if (moduleParts.length > 1) {
                resolved = resolved.map(
                  (r) => `${r}.${moduleParts.slice(1).join(".")}`
                );
              }
              resolvedModules = resolved;
            }
          }

          identifiers.push({
            name: `${prefix}.${baseName}`,
            type: "qualified",
            modules: resolvedModules,
            base: baseName,
            context: "function_call",
          });
        }
      } else if (node.type === "variable") {
        if (!this._is_in_binding_position(node)) {
          const varName = srcBytes
            .slice(node.startIndex, node.endIndex)
            .toString();
          const skipKeywords = new Set([
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
      } else if (node.type === "constructor") {
        const ctorName = srcBytes
          .slice(node.startIndex, node.endIndex)
          .toString();
        identifiers.push({
          name: ctorName,
          type: "type_constructor",
          context: "type_system",
        });
      } else if (node.type === "operator") {
        const opName = srcBytes
          .slice(node.startIndex, node.endIndex)
          .toString();
        identifiers.push({
          name: opName,
          type: "operator",
          context: "operation",
        });
      } else if (node.type === "integer") {
        const numVal = srcBytes
          .slice(node.startIndex, node.endIndex)
          .toString();
        identifiers.push({
          name: numVal,
          type: "literal",
          subtype: "numeric",
          value: numVal,
          context: "literal",
        });
      } else if (node.type === "float") {
        const numVal = srcBytes
          .slice(node.startIndex, node.endIndex)
          .toString();
        identifiers.push({
          name: numVal,
          type: "literal",
          subtype: "numeric",
          value: numVal,
          context: "literal",
        });
      } else if (node.type === "string") {
        const strVal = srcBytes
          .slice(node.startIndex, node.endIndex)
          .toString();
        identifiers.push({
          name: strVal,
          type: "literal",
          subtype: "string",
          context: "literal",
        });
      } else if (node.type === "list") {
        const listContent = srcBytes
          .slice(node.startIndex, node.endIndex)
          .toString();
        identifiers.push({
          name: listContent,
          type: "literal",
          subtype: "list",
          context: "literal",
        });
      } else if (node.type === "tuple") {
        const tupleContent = srcBytes
          .slice(node.startIndex, node.endIndex)
          .toString();
        const elementCount =
          (tupleContent.match(/,/g) || []).length + 1 > 1
            ? (tupleContent.match(/,/g) || []).length + 1
            : 2;
        identifiers.push({
          name: tupleContent,
          type: "literal",
          subtype: "tuple",
          length: elementCount,
          context: "literal",
        });
      } else if (node.type === "lambda") {
        identifiers.push({
          name: "λ",
          type: "lambda",
          context: "anonymous_function",
        });
      }

      for (const child of node.children) {
        traverseNode(child);
      }
    };

    traverseNode(functionNode);

    const seen = new Set<string>();
    const uniqueIdentifiers: FunctionCall[] = [];
    for (const ident of identifiers) {
      const key = `${ident.name},${ident.type},${ident.context}`;
      if (!seen.has(key)) {
        seen.add(key);
        uniqueIdentifiers.push(ident);
      }
    }

    return uniqueIdentifiers;
  }

  private _is_in_binding_position(node: SyntaxNode): boolean {
    const parent = node.parent;
    if (!parent) {
      return false;
    }

    if (parent.type === "bind") {
      const nameField = parent.childForFieldName("name");
      if (nameField && nameField.id === node.id) {
        return true;
      }
    } else if (parent.type === "function") {
      const nameField = parent.childForFieldName("name");
      if (nameField && nameField.id === node.id) {
        return true;
      }
      const patternsField = parent.childForFieldName("patterns");
      if (patternsField && this._node_contains_child(patternsField, node)) {
        return true;
      }
    } else if (["patterns", "pattern"].includes(parent.type)) {
      return true;
    } else if (parent.type === "signature") {
      const nameField = parent.childForFieldName("name");
      if (nameField && nameField.id === node.id) {
        return true;
      }
    } else if (parent.type === "local_binds") {
      return this._is_in_binding_position(parent);
    }

    return false;
  }

  private _node_contains_child(
    parentNode: SyntaxNode,
    targetNode: SyntaxNode
  ): boolean {
    if (parentNode.id === targetNode.id) {
      return true;
    }
    for (const child of parentNode.children) {
      if (this._node_contains_child(child, targetNode)) {
        return true;
      }
    }
    return false;
  }

  private extractWhereDefinitions(
    functionNode: SyntaxNode,
    srcBytes: Buffer
  ): WhereDefinition[] {
    const whereDefs: WhereDefinition[] = [];
    for (const node of functionNode.children) {
      if (node.type === "local_binds") {
        for (const bindNode of node.children) {
          if (bindNode.type !== "bind") continue;

          const nameNode = bindNode.childForFieldName("name");
          if (!nameNode) continue;

          const name = srcBytes
            .slice(nameNode.startIndex, nameNode.endIndex)
            .toString();
          const start = bindNode.startPosition.row;
          const end = bindNode.endPosition.row;
          const code = srcBytes
            .toString()
            .split("\n")
            .slice(start, end + 1)
            .join("\n");

          whereDefs.push({
            kind: "function",
            name: name,
            code: code,
          });
        }
      }
    }
    return whereDefs;
  }

  private extractImportComponent(
    importNode: SyntaxNode,
    srcBytes: Buffer
  ): Import | null {
    const start = importNode.startPosition.row;
    const end = importNode.endPosition.row;
    const importCode = srcBytes
      .toString()
      .split("\n")
      .slice(start, end + 1)
      .join("\n");
    const moduleNode = importNode.childForFieldName("module");
    const moduleName = moduleNode
      ? srcBytes.slice(moduleNode.startIndex, moduleNode.endIndex).toString()
      : null;
    const aliasNode = importNode.childForFieldName("alias");
    const alias = aliasNode
      ? srcBytes.slice(aliasNode.startIndex, aliasNode.endIndex).toString()
      : null;
    const importList: string[] = [];
    const namesNode = importNode.childForFieldName("names");
    if (namesNode) {
      for (const nameChild of namesNode.children) {
        if (nameChild.type === "import_name") {
          for (const idChild of nameChild.children) {
            if (["name", "variable"].includes(idChild.type)) {
              importList.push(
                srcBytes.slice(idChild.startIndex, idChild.endIndex).toString()
              );
            }
          }
        }
      }
    }
    const isQualified = importCode.includes("qualified");
    const isHiding = importCode.includes("hiding");

    if (!moduleName) return null;

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
  }

  private extractDataTypeComponent(
    dataNode: SyntaxNode,
    srcBytes: Buffer,
    importMap: Record<string, string[]>
  ): DataType | null {
    const start = dataNode.startPosition.row;
    const end = dataNode.endPosition.row;
    const dataCode = srcBytes
      .toString()
      .split("\n")
      .slice(start, end + 1)
      .join("\n");
    const dataName = this.extractDataTypeName(dataNode, srcBytes);
    let constructors: any[] = [];
    for (const child of dataNode.children) {
      if (child.type === "data_constructors") {
        constructors = this.extractDataConstructors(child, srcBytes);
      }
    }
    let derivingInfo: any = null;
    for (const child of dataNode.children) {
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
  }

  private extractDataTypeName(
    dataNode: SyntaxNode,
    srcBytes: Buffer
  ): string {
    const nameNode = dataNode.childForFieldName("name");
    if (nameNode) {
      return srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString();
    }
    return "UnknownDataType";
  }

  private extractDataConstructors(
    constructorsNode: SyntaxNode,
    srcBytes: Buffer
  ): any[] {
    const constructors: any[] = [];
    for (const child of constructorsNode.children) {
      if (child.type === "data_constructor") {
        const constructor = this.extractSingleConstructor(child, srcBytes);
        if (constructor) {
          constructors.push(constructor);
        }
      }
    }
    return constructors;
  }

  private extractSingleConstructor(
    constructorNode: SyntaxNode,
    srcBytes: Buffer
  ): any {
    const constructorInfo = {
      type: "constructor",
      name: "Unknown",
      fields: [],
    };
    for (const child of constructorNode.children) {
      if (child.type === "record") {
        constructorInfo.type = "record";
        constructorInfo.name = this.extractConstructorName(child, srcBytes);
        constructorInfo.fields = this.extractRecordFields(child, srcBytes);
      } else if (child.type === "constructor") {
        constructorInfo.name = srcBytes
          .slice(child.startIndex, child.endIndex)
          .toString();
      }
    }
    return constructorInfo;
  }

  private extractConstructorName(
    recordNode: SyntaxNode,
    srcBytes: Buffer
  ): string {
    const nameNode = recordNode.childForFieldName("constructor");
    if (nameNode) {
      return srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString();
    }
    return "UnknownConstructor";
  }

  private extractRecordFields(
    recordNode: SyntaxNode,
    srcBytes: Buffer
  ): any[] {
    const fields: any[] = [];
    const fieldsNode = recordNode.childForFieldName("fields");
    if (fieldsNode) {
      for (const fieldChild of fieldsNode.children) {
        if (fieldChild.type === "field") {
          const fieldInfo = this.extractFieldInfo(fieldChild, srcBytes);
          if (fieldInfo) {
            fields.push(fieldInfo);
          }
        }
      }
    }
    return fields;
  }

  private extractFieldInfo(fieldNode: SyntaxNode, srcBytes: Buffer): any {
    const nameNode = fieldNode.childForFieldName("name");
    const fieldName = nameNode
      ? srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString()
      : null;
    const typeNode = fieldNode.childForFieldName("type");
    const typeTxt = typeNode
      ? srcBytes.slice(typeNode.startIndex, typeNode.endIndex).toString()
      : null;
    let core = typeTxt;
    if (core && core.includes(" ")) {
      core = core.split(" ").pop()!;
    }
    let typeInfo;
    if (core && core.includes(".")) {
      const parts = core.split(".");
      const base = parts.pop()!;
      const modulePart = parts.join(".");
      const resolved = this.importMap[modulePart] || [modulePart];
      const modules = resolved.map((m) => `${m}.${base}`);
      typeInfo = {
        name: `${modulePart}.${base}`,
        type: "qualified",
        modules: modules,
        base: base,
        context: "type_constructor",
      };
    } else {
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
  }

  private _extractQualifiedType(
    qualifiedNode: SyntaxNode,
    srcBytes: Buffer
  ): any {
    const moduleBits: string[] = [];
    const moduleNode = qualifiedNode.childForFieldName("module");
    if (moduleNode) {
      for (const m of moduleNode.children) {
        if (m.type === "module_id") {
          moduleBits.push(
            srcBytes.slice(m.startIndex, m.endIndex).toString()
          );
        }
      }
    }
    const baseNode =
      qualifiedNode.childForFieldName("id") ||
      qualifiedNode.childForFieldName("name");
    const base = baseNode
      ? srcBytes.slice(baseNode.startIndex, baseNode.endIndex).toString()
      : "";
    const full = [...moduleBits, base].filter(Boolean).join(".");
    const first = moduleBits.length > 0 ? moduleBits[0] : null;
    let modules: string[];
    if (first && this.importMap[first]) {
      modules = this.importMap[first].map(
        (imp) => `${imp}.${moduleBits.slice(1).join(".")}`
      );
    } else {
      modules = moduleBits.length > 0 ? [moduleBits.join(".")] : [];
    }
    return { full, modules, base };
  }

  private extractTypeInfo(typeNode: SyntaxNode, srcBytes: Buffer): any {
    if (typeNode.type === "name") {
      return srcBytes.slice(typeNode.startIndex, typeNode.endIndex).toString();
    } else if (typeNode.type === "qualified") {
      return this.extractQualifiedType(typeNode, srcBytes);
    } else if (typeNode.type === "apply") {
      return this.extractAppliedType(typeNode, srcBytes);
    } else {
      return srcBytes.slice(typeNode.startIndex, typeNode.endIndex).toString();
    }
  }

  private extractQualifiedType(
    qualifiedNode: SyntaxNode,
    srcBytes: Buffer
  ): string {
    let modulePart = "";
    let idPart = "";
    const moduleNode = qualifiedNode.childForFieldName("module");
    if (moduleNode) {
      for (const moduleChild of moduleNode.children) {
        if (moduleChild.type === "module_id") {
          modulePart = srcBytes
            .slice(moduleChild.startIndex, moduleChild.endIndex)
            .toString();
        }
      }
    }
    const baseNode =
      qualifiedNode.childForFieldName("id") ||
      qualifiedNode.childForFieldName("name");
    if (baseNode) {
      idPart = srcBytes.slice(baseNode.startIndex, baseNode.endIndex).toString();
    }
    return modulePart && idPart ? `${modulePart}.${idPart}` : idPart;
  }

  private extractAppliedType(
    applyNode: SyntaxNode,
    srcBytes: Buffer
  ): string {
    let constructor = "";
    let argument: any = "";
    for (const child of applyNode.children) {
      if (child.type === "name") {
        constructor = srcBytes
          .slice(child.startIndex, child.endIndex)
          .toString();
      } else if (["qualified", "name"].includes(child.type)) {
        argument = this.extractTypeInfo(child, srcBytes);
      }
    }
    return constructor && argument ? `${constructor} ${argument}` : constructor;
  }

  private extractDerivingClause(
    derivingNode: SyntaxNode,
    srcBytes: Buffer
  ): any {
    const derivingInfo: { strategy: string | null; classes: string[] } = {
      strategy: null,
      classes: [],
    };
    for (const child of derivingNode.children) {
      if (child.type === "deriving_strategy") {
        derivingInfo.strategy = srcBytes
          .slice(child.startIndex, child.endIndex)
          .toString();
      } else if (child.type === "tuple") {
        for (const tupleChild of child.children) {
          if (tupleChild.type === "name") {
            const className = srcBytes
              .slice(tupleChild.startIndex, tupleChild.endIndex)
              .toString();
            derivingInfo.classes.push(className);
          }
        }
      }
    }
    return derivingInfo;
  }

  private extractInstanceComponent(
    instanceNode: SyntaxNode,
    srcBytes: Buffer,
    importMap: Record<string, string[]>
  ): Instance | null {
    const start = instanceNode.startPosition.row;
    const end = instanceNode.endPosition.row;
    const instanceCode = srcBytes
      .toString()
      .split("\n")
      .slice(start, end + 1)
      .join("\n");
    const instanceName = this.extractInstanceName(instanceNode, srcBytes);
    const typePatterns = this.extractTypePatterns(instanceNode, srcBytes);
    const instanceMethods: any[] = [];
    const typeInstances: any[] = [];

    for (const child of instanceNode.children) {
      if (child.type === "instance_declarations") {
        for (const decl of child.children) {
          if (decl.type === "declaration") {
            for (const innerDecl of decl.children) {
              if (innerDecl.type === "bind") {
                const method = this.extractInstanceMethod(
                  innerDecl,
                  srcBytes,
                  importMap
                );
                if (method) {
                  instanceMethods.push(method);
                }
              } else if (innerDecl.type === "type_instance") {
                const typeInst = this.extractTypeInstance(innerDecl, srcBytes);
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
  }

  private extractInstanceName(
    instanceNode: SyntaxNode,
    srcBytes: Buffer
  ): string {
    const nameNode = instanceNode.childForFieldName("name");
    if (nameNode) {
      return srcBytes.slice(nameNode.startIndex, nameNode.endIndex).toString();
    }
    return "UnknownInstance";
  }

  private extractTypePatterns(
    instanceNode: SyntaxNode,
    srcBytes: Buffer
  ): any[] {
    const patterns: any[] = [];
    const typePatternsNode = instanceNode.childForFieldName("type_patterns");
    if (typePatternsNode) {
      for (const pattern of typePatternsNode.children) {
        if (pattern.type === "qualified") {
          const qualifiedInfo = this.extractQualifiedInfo(pattern, srcBytes);
          patterns.push(qualifiedInfo);
        } else {
          const patternText = srcBytes
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
  }

  private extractQualifiedInfo(
    qualifiedNode: SyntaxNode,
    srcBytes: Buffer
  ): any {
    let modulePart = "";
    let idPart = "";
    const moduleNode = qualifiedNode.childForFieldName("module");
    if (moduleNode) {
      for (const moduleChild of moduleNode.children) {
        if (moduleChild.type === "module_id") {
          modulePart = srcBytes
            .slice(moduleChild.startIndex, moduleChild.endIndex)
            .toString();
        }
      }
    }
    const baseNode =
      qualifiedNode.childForFieldName("id") ||
      qualifiedNode.childForFieldName("name");
    if (baseNode) {
      idPart = srcBytes.slice(baseNode.startIndex, baseNode.endIndex).toString();
    }

    if (modulePart && idPart) {
      const fullName = `${modulePart}.${idPart}`;
      const resolvedModules = this.importMap[modulePart] || [modulePart];
      return {
        name: fullName,
        type: "qualified",
        modules: resolvedModules,
        base: idPart,
        context: "type_pattern",
      };
    } else if (idPart) {
      return {
        name: idPart,
        type: "simple",
        context: "type_pattern",
      };
    } else {
      const fallbackName = srcBytes
        .slice(qualifiedNode.startIndex, qualifiedNode.endIndex)
        .toString();
      return {
        name: fallbackName,
        type: "fallback",
        context: "type_pattern",
      };
    }
  }

  private extractInstanceMethod(
    bindNode: SyntaxNode,
    srcBytes: Buffer,
    importMap: Record<string, string[]>
  ): any {
    let methodName = "";
    const nameNode = bindNode.childForFieldName("name");
    if (nameNode) {
      methodName = srcBytes
        .slice(nameNode.startIndex, nameNode.endIndex)
        .toString();
    }
    const start = bindNode.startPosition.row;
    const end = bindNode.endPosition.row;
    const methodCode = srcBytes
      .toString()
      .split("\n")
      .slice(start, end + 1)
      .join("\n");
    return {
      kind: "instance_method",
      name: methodName,
      code: methodCode.trim(),
    };
  }

  private extractTypeInstance(
    typeInstanceNode: SyntaxNode,
    srcBytes: Buffer
  ): any {
    let typeName = "";
    const nameNode = typeInstanceNode.childForFieldName("name");
    if (nameNode) {
      typeName = srcBytes
        .slice(nameNode.startIndex, nameNode.endIndex)
        .toString();
    }
    const typePatterns: any[] = [];
    const typePatternsNode = typeInstanceNode.childForFieldName("type_patterns");
    if (typePatternsNode) {
      for (const pattern of typePatternsNode.children) {
        if (pattern.type === "qualified") {
          const qualifiedInfo = this.extractQualifiedInfo(pattern, srcBytes);
          typePatterns.push(qualifiedInfo);
        } else {
          const patternText = srcBytes
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
    let typeDefinition: any = "";
    const valueNode = typeInstanceNode.childForFieldName("value");
    if (valueNode) {
      if (valueNode.type === "qualified") {
        typeDefinition = this.extractQualifiedInfo(valueNode, srcBytes);
      } else {
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
  }

  private extractFunctionCalls(
    funcCode: string,
    importMap: Record<string, string[]>,
    currentModule: string
  ): FunctionCall[] {
    return [];
  }

  private findTypeDependencies(
    funcName: string,
    components: Component[]
  ): string[] {
    for (const comp of components) {
      if (comp.kind === "function" && comp.name === funcName) {
        const sig = comp.typeSignature;
        if (!sig) {
          return [];
        }
        const typePart = sig.split("::", 2)[1];
        const deps = typePart.match(/\b[A-Z][A-Za-z0-9_.]*\b/g) || [];
        return [...new Set(deps)].sort();
      }
    }
    return [];
  }
}
