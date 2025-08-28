import * as fs from "fs";
import * as path from "path";
import { HaskellComponentExtractor } from "./extractors/haskell_extractor";
import { TypeScriptComponentExtractor } from "./extractors/typescript_extractor";
import { adaptHaskellComponents } from "./adapters/haskell_adapter";
import { adaptTypeScriptComponents } from "./adapters/typescript_adapter";
import { RustComponentExtractor } from "./extractors/rust_extractor";
import { adaptRustComponents } from "./adapters/rust_adapter";
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


  const allHaskellComponents: any[] = [];
  const allRustComponents: any[] = [];
  const allTscomponenets: any[] = [];

  function walk(dir: string) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
      const fullPath = path.join(dir, file);
      if (fs.statSync(fullPath).isDirectory()) {
        walk(fullPath);
      } else if (path.extname(fullPath) === ".hs" || path.extname(fullPath) === ".ts") {
        try {
            const fileContent = fs.readFileSync(fullPath, "utf-8");
            if (fileContent.trim().length === 0) {
                console.log(`Skipping empty file: ${fullPath}`);
                continue;
            }
            console.log(`Processing ${fullPath}`);
            let extractor;
            if (path.extname(fullPath) === ".hs") {
                extractor = new HaskellComponentExtractor();
                extractor.processFile(fullPath);
                allHaskellComponents.push(...extractor.extractAllComponents());
            } else if (path.extname(fullPath) === ".ts") {
                extractor = new TypeScriptComponentExtractor();
                extractor.processFile(fullPath);
                allTscomponenets.push(...extractor.extractAllComponents());
            }
            else if (path.extname(fullPath) === ".rs") {
                extractor = new RustComponentExtractor();
                extractor.processFile(fullPath);
                allRustComponents.push(...extractor.extractAllComponents());
            }
            else {
                console.log(`Unsupported file type: ${fullPath}`);
                continue;
            }

        } catch (e: any) {
            console.error(`Error processing file ${fullPath}:`, e.message);
        }
      }
    }
  }

  walk(repoPath);
  
  let adaptedComponents;
  if (process.argv[3] === 'haskell') {
      adaptedComponents = adaptHaskellComponents(allHaskellComponents);
  } else if (process.argv[3] ===  'typescript') {
      adaptedComponents = adaptTypeScriptComponents(allTscomponenets);
  }
  else if (process.argv[3] ===  'rust') {
      adaptedComponents = adaptRustComponents(allRustComponents);
  } else {
      console.error("Please provide a valid language: haskell, typescript or rust");
      return;
  }
  const { nodes, edges } = adaptedComponents;
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
