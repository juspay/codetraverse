import * as fs from "fs";
import * as path from "path";
import * as jsnx from "jsnetworkx";
import { Component } from "../types/types";

function loadComponents(fdepDir: string): Record<string, Component> {
  const funcs: Record<string, Component> = {};
  for (const dirpath of fs.readdirSync(fdepDir)) {
    const fullpath = path.join(fdepDir, dirpath);
    if (fs.statSync(fullpath).isDirectory()) {
      for (const fn of fs.readdirSync(fullpath)) {
        if (!fn.endsWith(".json")) {
          continue;
        }
        const subpath = path.join(fullpath, fn);
        const data = JSON.parse(fs.readFileSync(subpath, "utf-8"));
        for (const comp of data) {
          const fq = `${comp.module}::${comp.name}`;
          funcs[fq] = comp;
        }
      }
    }
  }
  return funcs;
}

function loadComponentsWithoutHash(fdepDir: string): Component[] {
  const components: Component[] = [];
  for (const dirpath of fs.readdirSync(fdepDir)) {
    const fullpath = path.join(fdepDir, dirpath);
    if (fs.statSync(fullpath).isDirectory()) {
      for (const fn of fs.readdirSync(fullpath)) {
        if (!fn.endsWith(".json")) {
          continue;
        }
        const subpath = path.join(fullpath, fn);
        const data = JSON.parse(fs.readFileSync(subpath, "utf-8"));
        components.push(...data);
      }
    }
  }
  return components;
}

export function buildGraphFromSchema(schema: {
  nodes: any[];
  edges: any[];
}): jsnx.DiGraph {
  const G = new jsnx.DiGraph();

  for (const node of schema.nodes) {
    const nid = node.id;
    const attrs: Record<string, any> = {};
    for (const k in node) {
      if (k === "id") {
        continue;
      }
      const v = node[k];
      if (v === null) {
        attrs[k] = "";
      } else if (
        typeof v === "string" ||
        typeof v === "number" ||
        typeof v === "boolean"
      ) {
        attrs[k] = v;
      } else {
        attrs[k] = JSON.stringify(v);
      }
    }
    G.addNode(nid, attrs);
  }

  for (const edge of schema.edges) {
    const src = edge.from;
    const dst = edge.to;
    const rel = edge.relation || "";
    G.addEdge(src, dst, { relation: rel });
  }

  return G;
}

function preprocessGraph(G: jsnx.DiGraph): jsnx.DiGraph {
  const nodesToRemove = G.nodes(true).filter(
    ([, attrs]) => attrs.code === ""
  );
  for (const [node] of nodesToRemove) {
    G.removeNode(node);
  }
  return G;
}

export function buildCleanGraph(
  folderPath: string,
  saveAsJson = false,
  outputPath = ""
): jsnx.DiGraph {
  const jsonFolder = folderPath;
  const fdepNx = buildGraphFromFolder(
    jsonFolder,
    saveAsJson,
    outputPath
  );
  const fdepNxProcessed = preprocessGraph(fdepNx);
  return fdepNxProcessed;
}

function buildGraphFromFolder(
  folderPath: string,
  saveAsJson = false,
  outputPath = ""
): jsnx.DiGraph {
  const G = new jsnx.DiGraph();
  for (const root of fs.readdirSync(folderPath)) {
    const fullPath = path.join(folderPath, root);
    if (fs.statSync(fullPath).isDirectory()) {
      for (const fname of fs.readdirSync(fullPath)) {
        if (!fname.endsWith(".json")) {
          continue;
        }
        const subpath = path.join(fullPath, fname);
        try {
          const data = JSON.parse(fs.readFileSync(subpath, "utf-8"));
          processModule(data, G);
        } catch (e) {
          console.error(e);
          continue;
        }
      }
    }
  }
  if (saveAsJson) {
    graphToJson(G, outputPath);
  }
  return G;
}

function graphToJson(G: jsnx.DiGraph, outputPath: string): void {
  const nodes = G.nodes(true).map(([node, attrs]) => ({
    id: node,
    ...attrs,
  }));
  const edges = G.edges(true).map(([u, v, attrs]) => ({
    from: u,
    to: v,
    ...attrs,
  }));
  const graphData = { nodes, edges };
  fs.writeFileSync(
    path.join(outputPath, "fdep.json"),
    JSON.stringify(graphData, null, 2)
  );
}

function addLineNum(node: any): string {
  const resCode: string[] = [];
  const ogCode = node.code || "";
  const start = node.start_line || -1;
  const end = node.end_line || -1;
  if (start < 0 || end < 0) {
    return ogCode;
  }
  const lines = ogCode.split("\n");
  const maxLineNumLen = (lines.length + 1).toString().length;
  for (let i = 0; i < lines.length; i++) {
    const lineNum = (i + start).toString().padStart(maxLineNumLen, " ");
    const formattedLine = `${lineNum} | ${lines[i]}`;
    resCode.push(formattedLine);
  }
  return resCode.join("\n");
}

function addOrUpdateNode(
  G: jsnx.DiGraph,
  key: string,
  meta: any,
  mergeLists = true
): void {
  if (!G.hasNode(key)) {
    G.addNode(key, meta);
    return;
  }
  const existing = G.node.get(key);
  for (const k in meta) {
    const v = meta[k];
    if (mergeLists && Array.isArray(v) && Array.isArray(existing[k])) {
      existing[k] = [...new Set([...existing[k], ...v])];
    } else {
      existing[k] = v;
    }
  }
}

function processModule(moduleData: any[], G: jsnx.DiGraph): void {
  for (const node of moduleData) {
    if (typeof node !== "object" || node === null) {
      continue;
    }
    if (node.kind !== "function") {
      continue;
    }
    const nodeKey = `${node.name || "_"}--${node.module || "_"}`;
    const children = new Set<string>();
    for (const c of node.function_calls || []) {
      if (typeof c === "object" && c !== null && c.context === "function_call") {
        children.add(`${c.base || "_"}--${(c.modules && c.modules[0]) || "_"}`);
      }
    }
    const nodeMeta = {
      code: addLineNum(node),
      type_signature: node.type_signature || "",
      types_used: node.type_dependencies || [],
    };
    addOrUpdateNode(G, nodeKey, nodeMeta, false);
    for (const ck of children) {
      if (!G.hasNode(ck)) {
        G.addNode(ck);
      }
      G.addEdge(nodeKey, ck);
    }
  }
}

function topRootsByDescendants(
  G: jsnx.DiGraph,
  topN = 10
): [string, number][] {
  const roots = G.nodes().filter((n) => G.inDegree(n) === 0);
  const rootCounts: [string, number][] = [];
  for (const r of roots) {
    const count = jsnx.descendants(G, r).length;
    rootCounts.push([r, count]);
  }
  rootCounts.sort((a, b) => a[1] - b[1]);
  return rootCounts.slice(0, topN);
}
