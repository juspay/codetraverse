import * as fs from "fs";
import * as path from "path";
import { HaskellComponentExtractor } from "./extractors/haskell_extractor";
import { adaptHaskellComponents } from "./adapters/haskell_adapter";
import { buildGraphFromSchema } from "./utils/jsnetworkx_graph";

function main() {
  const repoPath = process.argv[2];
  if (!repoPath) {
    console.error("Please provide a repo path.");
    return;
  }

  if (!fs.existsSync(repoPath)) {
    console.error(`Error: Path not found at ${repoPath}`);
    return;
  }

  const outputDir = "output";
  fs.mkdirSync(outputDir, { recursive: true });
  const fdepDir = path.join(outputDir, "fdep");
  fs.mkdirSync(fdepDir, { recursive: true });
  const graphDir = path.join(outputDir, "graph");
  fs.mkdirSync(graphDir, { recursive: true });


  const allComponents: any[] = [];
  function walk(dir: string) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
      const fullPath = path.join(dir, file);
      if (fs.statSync(fullPath).isDirectory()) {
        walk(fullPath);
      } else if (path.extname(fullPath) === ".hs") {
        try {
            const fileContent = fs.readFileSync(fullPath, "utf-8");
            if (fileContent.trim().length === 0) {
                console.log(`Skipping empty file: ${fullPath}`);
                continue;
            }
            console.log(`Processing ${fullPath}`);
            const extractor = new HaskellComponentExtractor();
            extractor.processFile(fullPath);
            allComponents.push(...extractor.extractAllComponents());
        } catch (e: any) {
            console.error(`Error processing file ${fullPath}:`, e.message);
        }
      }
    }
  }

  walk(repoPath);
  
  const { nodes, edges } = adaptHaskellComponents(allComponents);
  const graph = buildGraphFromSchema({ nodes, edges });

  const graphData = {
    nodes: graph.nodes(true).map(([node, attrs]) => ({ id: node, ...attrs })),
    edges: graph.edges(true).map(([u, v, attrs]) => ({ from: u, to: v, ...attrs })),
  };

  const outputPath = path.join(graphDir, "fdep.json");
  fs.writeFileSync(outputPath, JSON.stringify(graphData, null, 2), "utf-8");
  console.log(`Successfully extracted components to ${outputPath}`);
}

main();
