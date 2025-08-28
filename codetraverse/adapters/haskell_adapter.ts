import { Component, FunctionCall } from "../types/types";

interface Node {
  id: string;
  category: string;
  name: string;
  file_path: string;
  location?: {
    start?: number;
    end?: number;
  };
}

interface Edge {
  from: string;
  to: string;
  relation: string;
}

export function adaptHaskellComponents(rawComponents: Component[]): {
  nodes: Node[];
  edges: Edge[];
} {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const nodeIds = new Set<string>();

  const allCompsByModule: Record<string, Component[]> = {};
  const mainModulesByFile: Record<string, string> = {};

  for (const comp of rawComponents) {
    if (comp.kind === "module_header") {
      mainModulesByFile[comp.filePath!] = comp.name;
    }
  }

  for (const comp of rawComponents) {
    const name = comp.name;
    const filePath = comp.filePath;
    if (!name || !filePath) continue;

    const compModule = comp.module || mainModulesByFile[filePath];
    if (!compModule) continue;

    comp.module = compModule;
    if (!allCompsByModule[compModule]) {
      allCompsByModule[compModule] = [];
    }
    allCompsByModule[compModule].push(comp);
  }

  const compsByFile: Record<string, Component[]> = {};
  for (const comp of rawComponents) {
    if (comp.filePath) {
      if (!compsByFile[comp.filePath]) {
        compsByFile[comp.filePath] = [];
      }
      compsByFile[comp.filePath].push(comp);
    }
  }

  for (const filePath in compsByFile) {
    const fileComps = compsByFile[filePath];
    const importAliasMap: Record<string, string> = {};
    for (const imp of fileComps) {
      if (imp.kind === "import" && imp.alias) {
        importAliasMap[imp.alias] = imp.module!;
      }
    }

    for (const comp of fileComps) {
      const { kind, name, module: compModule } = comp;
      if (!kind || !name || !compModule) continue;

      const sourceId = `${compModule}::${name}`;
      if (!nodeIds.has(sourceId)) {
        let nodeCategory = kind;
        if (kind === "module_header") nodeCategory = "module";
        if (kind === "class") nodeCategory = "typeclass";

        nodes.push({
          id: sourceId,
          category: nodeCategory,
          name: name,
          file_path: comp.filePath || "",
          location: { start: comp.startLine, end: comp.endLine },
        });
        nodeIds.add(sourceId);
      }

      if (kind === "module_header") {
        for (const exportName of comp.exports || []) {
          if (importAliasMap[exportName]) {
            const alias = exportName;
            const actualModuleNames = fileComps
              .filter((imp) => imp.alias === alias)
              .map((imp) => imp.module);

            for (const actualModuleName of actualModuleNames) {
              for (const targetComp of allCompsByModule[actualModuleName!] ||
                []) {
                const targetName = targetComp.name;
                if (!targetName) continue;

                const proxyId = `${compModule}::${targetName}`;
                if (!nodeIds.has(proxyId)) {
                  nodes.push({
                    id: proxyId,
                    category: "reexport",
                    name: targetName,
                    file_path: comp.filePath || "",
                    location: {},
                  });
                  nodeIds.add(proxyId);
                }

                edges.push({
                  from: sourceId,
                  to: proxyId,
                  relation: "exports",
                });
                const actualId = `${targetComp.module}::${targetName}`;
                edges.push({
                  from: proxyId,
                  to: actualId,
                  relation: "reexport_of",
                });
              }
            }
          } else {
            edges.push({
              from: sourceId,
              to: `${compModule}::${exportName}`,
              relation: "exports",
            });
          }
        }
      } else if (kind === "function") {
        for (const call of comp.functionCalls || []) {
          const callBase = call.base || call.name;
          if (!callBase) continue;
          const targetModule = (call.modules && call.modules[0]) || compModule;
          edges.push({
            from: sourceId,
            to: `${targetModule}::${callBase}`,
            relation: "calls",
          });
        }

        for (const dep of comp.typeDependencies || []) {
          const parts = dep.split(".");
          const depName = parts.pop()!;
          const depMod = parts.join(".");
          edges.push({
            from: sourceId,
            to: `${depMod || compModule}::${depName}`,
            relation: "uses_type",
          });
        }
      } else if (kind === "instance") {
        const className = comp.name.split(" ")[0];
        const classId = `${compModule}::${className}`;
        edges.push({ from: sourceId, to: classId, relation: "implements" });
      }
    }
  }

  const allNodeIdsFinal = new Set(nodes.map((n) => n.id));
  for (const edge of edges) {
    for (const endpoint of ["from", "to"]) {
      const edgePoint = edge[endpoint as keyof Edge];
      if (!allNodeIdsFinal.has(edgePoint)) {
        nodes.push({
          id: edgePoint,
          category: "external",
          name: edgePoint.split("::").pop()!,
          file_path: "external",
        });
        allNodeIdsFinal.add(edgePoint);
      }
    }
  }

  console.log(`Adapted ${nodes.length} nodes and ${edges.length} edges`);
  return { nodes, edges };
}
