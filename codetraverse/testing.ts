import * as fs from "fs";
import * as path from "path";
import { HaskellComponentExtractor } from "./extractors/haskell_extractor";

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

  const outputDir = "output/fdep";
  fs.mkdirSync(outputDir, { recursive: true });

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
            const components = extractor.extractAllComponents();
            const relativePath = path.relative(repoPath, fullPath);
            const outputDirPath = path.join(outputDir, path.dirname(relativePath));
            fs.mkdirSync(outputDirPath, { recursive: true });
            const outputFileName = path.basename(relativePath) + ".json";
            const outputPath = path.join(outputDirPath, outputFileName);
            fs.writeFileSync(outputPath, JSON.stringify(components, null, 2), "utf-8");
            console.log(`Successfully extracted components to ${outputPath}`);
        } catch (e: any) {
            console.error(`Error processing file ${fullPath}:`, e.message);
        }
      }
    }
  }

  walk(repoPath);
}

main();
