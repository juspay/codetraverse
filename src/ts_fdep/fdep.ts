#!/usr/bin/env node

import {
  Project,
  Node,
  SyntaxKind,
  CallExpression,
  Symbol as MorphSymbol,
} from "ts-morph";
import * as path from "path";
import { writeFileSync } from "fs";
import { execSync } from "child_process";
import * as fs from "fs";

enum NodeType {
  Function = "Function",
  Method = "Method",
  Class = "Class",
  Type = "Type",
  Enum = "Enum",
  Interface = "Interface",
  VariableFunction = "VariableFunction",
  Getter = "Getter",
  Setter = "Setter",
  Unknown = "Unknown",
}

interface GraphNode {
  id: string;
  file: string;
  label: string;
  code: string;
  signature: string;
  nodeType: NodeType;
  typesUsed: string[];
  dependsOn: string[];
}

interface Graph {
  nodes: Record<string, GraphNode>;
  edges: Array<[string, string]>;
}

/* -------------------------------------------------------------- */
/* helpers                                                        */
/* -------------------------------------------------------------- */

function sanitizedPath(tscDirPath: string, fp: string) {
  return path.relative(tscDirPath, fp).replace(/\\/g, "/");
}

/**
 * Deterministic ID format:
 *   file_path::className::interfaceName::enumName::name
 */
function buildDeclId(node: Node, tscDirPath: string): string {
  const file = sanitizedPath(tscDirPath, node.getSourceFile().getFilePath());
  const parts = [file];

  const cls = node.getFirstAncestorByKind(SyntaxKind.ClassDeclaration);
  if (cls?.getName()) parts.push(cls.getName()!);

  const iface = node.getFirstAncestorByKind(SyntaxKind.InterfaceDeclaration);
  if (iface?.getName()) parts.push(iface.getName()!);

  const en = node.getFirstAncestorByKind(SyntaxKind.EnumDeclaration);
  if (en?.getName()) parts.push(en.getName()!);

  const any = node as any;
  if (any.getName && any.getName()) {
    parts.push(any.getName());
  } else {
    // Skip anonymous items to avoid unstable graph
    parts.push("<anonymous>");
  }

  return parts.join("::");
}

function labelFor(node: Node): string {
  const any = node as any;
  if (any.getName) {
    const n = any.getName();
    if (n) return n;
  }
  return `${SyntaxKind[node.getKind()]}`;
}

function typeSig(node: Node): string {
  try {
    const t = (node as any).getType?.();
    if (t) return t.getText(node.getSourceFile());
  } catch {}
  return "<unknown>";
}

/* -------------------------------------------------------------- */
/* register                                                       */
/* -------------------------------------------------------------- */

function register(nodes: Map<string, GraphNode>, node: Node, type: NodeType, tsconfigPath: string) {
  const id = buildDeclId(node, tsconfigPath);
  if (id.includes("<anonymous>")) return; // Skip anonymous nodes
  if (nodes.has(id)) return;

  nodes.set(id, {
    id,
    file: sanitizedPath(tsconfigPath, node.getSourceFile().getFilePath()),
    label: labelFor(node),
    code: node.getText(),
    signature: typeSig(node),
    nodeType: type,
    typesUsed: [],
    dependsOn: [],
  });
}

/* -------------------------------------------------------------- */
/* definition detection                                           */
/* -------------------------------------------------------------- */

function isDefinition(node: Node): boolean {
  if (Node.isFunctionDeclaration(node)) return true;
  if (Node.isMethodDeclaration(node)) return true;
  if (Node.isClassDeclaration(node)) return true;
  if (Node.isInterfaceDeclaration(node)) return true;
  if (Node.isEnumDeclaration(node)) return true;
  if (Node.isTypeAliasDeclaration(node)) return true;
  if (Node.isGetAccessorDeclaration(node)) return true;
  if (Node.isSetAccessorDeclaration(node)) return true;

  // Named variable = function
  if (Node.isVariableDeclaration(node)) {
    const init = node.getInitializer();
    if (
      node.getName() &&
      init &&
      (Node.isFunctionExpression(init) || Node.isArrowFunction(init))
    ) {
      return true;
    }
  }

  // NO anonymous lambdas, property lambdas, inline callbacks
  return false;
}

/* -------------------------------------------------------------- */
/* call resolution                                                */
/* -------------------------------------------------------------- */

function resolveCall(call: CallExpression): Node[] {
  const expr = call.getExpression();
  const syms: MorphSymbol[] = [];

  function push(s?: MorphSymbol) {
    if (s) syms.push(s);
  }

  try {
    push(expr.getSymbol?.());
  } catch {}

  try {
    push((expr as any).getType?.()?.getSymbol?.());
  } catch {}

  if (Node.isPropertyAccessExpression(expr)) {
    try {
      push(expr.getNameNode().getSymbol?.());
    } catch {}
  }

  const decls: Node[] = [];

  for (let sym of syms) {
    if (!sym) continue;

    try {
      const aliased = sym.getAliasedSymbol?.();
      if (aliased) sym = aliased;
    } catch {}

    for (const d of sym.getDeclarations?.() ?? []) {
      decls.push(d);
    }
  }

  return decls;
}

/* -------------------------------------------------------------- */
/* typesUsed collector                                             */
/* -------------------------------------------------------------- */

function collectTypesUsed(node: Node, nodes: Map<string, GraphNode>, tscDirPath: string): string[] {
  const refs = node.getDescendantsOfKind(SyntaxKind.TypeReference);
  const out = new Set<string>();

  for (const tr of refs) {
    const sym = tr.getType().getSymbol?.();
    if (!sym) continue;

    const real = sym.getAliasedSymbol?.() ?? sym;
    for (const d of real.getDeclarations?.() ?? []) {
      const id = buildDeclId(d, tscDirPath);
      if (!id.includes("<anonymous>") && nodes.has(id)) {
        out.add(id);
      }
    }
  }
  return [...out];
}

/* -------------------------------------------------------------- */
/* dependsOn collector (extends/implements/intersections)         */
/* -------------------------------------------------------------- */

function collectDependsOn(node: Node, nodes: Map<string, GraphNode>, tscDirPath: string): string[] {
  const deps = new Set<string>();

  const addTypeNode = (t: any) => {
    const sym = t.getType().getSymbol?.();
    if (!sym) return;

    const real = sym.getAliasedSymbol?.() ?? sym;
    for (const d of real.getDeclarations?.() ?? []) {
      const id = buildDeclId(d, tscDirPath);
      if (!id.includes("<anonymous>") && nodes.has(id)) {
        deps.add(id);
      }
    }
  };

  if (Node.isClassDeclaration(node) || Node.isInterfaceDeclaration(node)) {
    for (const clause of node.getHeritageClauses() ?? []) {
      for (const t of clause.getTypeNodes()) addTypeNode(t);
    }
  }

  if (Node.isTypeAliasDeclaration(node)) {
    const typeNode = node.getTypeNode();
    if (typeNode && Node.isIntersectionTypeNode(typeNode)) {
      for (const t of typeNode.getTypeNodes()) addTypeNode(t);
    }
  }

  return [...deps];
}

/* -------------------------------------------------------------- */
/* main graph builder                                             */
/* -------------------------------------------------------------- */

export function buildGraph(tsconfigPath: string): Graph {
  const project = new Project({ tsConfigFilePath: tsconfigPath });

  const nodes = new Map<string, GraphNode>();
  const edgesSet = new Set<string>();
  const edges: Array<[string, string]> = [];
  const tscPath = path.parse(tsconfigPath)

  /* 1. collect definitions */
  for (const sf of project.getSourceFiles()) {
    sf.forEachDescendant((node) => {
      if (!isDefinition(node)) return;

      let t = NodeType.Unknown;
      if (Node.isFunctionDeclaration(node)) t = NodeType.Function;
      else if (Node.isMethodDeclaration(node)) t = NodeType.Method;
      else if (Node.isClassDeclaration(node)) t = NodeType.Class;
      else if (Node.isInterfaceDeclaration(node)) t = NodeType.Interface;
      else if (Node.isEnumDeclaration(node)) t = NodeType.Enum;
      else if (Node.isTypeAliasDeclaration(node)) t = NodeType.Type;
      else if (Node.isGetAccessorDeclaration(node)) t = NodeType.Getter;
      else if (Node.isSetAccessorDeclaration(node)) t = NodeType.Setter;
      else if (Node.isVariableDeclaration(node)) t = NodeType.VariableFunction;

      register(nodes, node, t, tscPath.dir);
    });
  }

  /* 2. compute call edges + typesUsed + dependsOn */
  for (const sf of project.getSourceFiles()) {
    sf.forEachDescendant((node) => {
      if (!isDefinition(node)) return;

      const id = buildDeclId(node, tscPath.dir);
      if (!nodes.has(id)) return;

      // calls
      const calls = node.getDescendantsOfKind(SyntaxKind.CallExpression);
      for (const c of calls) {
        const decls = resolveCall(c);
        for (const d of decls) {
          const tid = buildDeclId(d, tscPath.dir);
          if (!tid.includes("<anonymous>") && nodes.has(tid)) {
            const key = `${id}|${tid}`;
            if (!edgesSet.has(key)) {
              edgesSet.add(key);
              edges.push([id, tid]);
            }
          }
        }
      }

      nodes.get(id)!.typesUsed = collectTypesUsed(node, nodes, tscPath.dir);
      nodes.get(id)!.dependsOn = collectDependsOn(node, nodes, tscPath.dir);
    });
  }

  /* 3. finalize */
  const outNodes: Record<string, GraphNode> = {};
  for (const [id, n] of nodes.entries()) outNodes[id] = n;

  return { nodes: outNodes, edges };
}

function run(cmd: string) {
  try {
    return execSync(cmd, { stdio: "inherit" });
  } catch (err) {
    throw new Error(`Command failed: ${cmd}\n${err}`);
  }
}

export function setupAndRunPython(
  requirementsPath: string,
  scriptToRun: string
) {
  // --- 1. Check Python ---
  let pythonCmd = "";
  try {
    execSync("python3 --version");
    pythonCmd = "python3";
  } catch {
    try {
      execSync("python --version");
      pythonCmd = "python";
    } catch {
      throw new Error("Python is not installed or not in PATH.");
    }
  }

  // --- 2. Validate files ---
  if (!fs.existsSync(requirementsPath)) {
    throw new Error("requirements.txt not found.");
  }

  if (!fs.existsSync(scriptToRun)) {
    throw new Error("Target Python file not found.");
  }
  // --- 3. Install requirements ---
  run(`${pythonCmd} -m pip install -r ${requirementsPath}`);

  run(`${pythonCmd} -c 'print("HELLO")'`)

  // --- 4. Run the script ---
  // run(`${pythonCmd} ${scriptToRun}`);
}




/* -------------------------------------------------------------- */
/* CLI                                                            */
/* -------------------------------------------------------------- */

function parseArgs() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error("Error: <tsconfig_pth> is required.");
    process.exit(1);
  }

  const parsed: {
    tsconfigPath: string;
    outputDir?: string;
    push?: boolean;
  } = {
    tsconfigPath: args[0],
  };

  for (let i = 1; i < args.length; i++) {
    const a = args[i];

    if ((a === "-o" || a === "--outputDir") && args[i + 1]) {
      parsed.outputDir = args[++i];
    } else {
      console.warn(`Ignoring unknown option: ${a}`);
    }
  }

  return parsed;
}

function main() {
  const args = parseArgs();

  const g = buildGraph(args.tsconfigPath);
  console.log(`Nodes: ${Object.keys(g.nodes).length}  Edges: ${g.edges.length}`);

  const outputDir = args.outputDir || "./";
  const outputPath = path.join(outputDir, "fdep-output.json");

  writeFileSync(outputPath, JSON.stringify(g, null, 2), "utf-8");

  if (args.push) {
    console.log("PUSHED");
  }
}

if (require.main === module) {
  main();
}


// if (require.main === module) {
//   const tsconfig = process.argv[2] || path.join(process.cwd(), "tsconfig.json");
//   const g = buildGraph(tsconfig);
//   const out = path.join(process.cwd(), "fdep-output.json");
//   writeFileSync(out, JSON.stringify(g, null, 2), "utf-8");
//   console.log(`Generated graph → ${out}`);
//   console.log(`Nodes: ${Object.keys(g.nodes).length}  Edges: ${g.edges.length}`);
// }
