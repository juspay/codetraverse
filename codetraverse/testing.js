"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
var fs = require("fs");
var path = require("path");
var haskell_extractor_1 = require("./extractors/haskell_extractor");
function main() {
    var filePath = process.argv[2];
    if (!filePath) {
        console.error("Please provide a file path.");
        return;
    }
    if (!fs.existsSync(filePath)) {
        console.error("Error: File not found at ".concat(filePath));
        return;
    }
    var extractor = new haskell_extractor_1.HaskellComponentExtractor();
    extractor.processFile(filePath);
    var components = extractor.extractAllComponents();
    var outputDir = "output/fdep";
    fs.mkdirSync(outputDir, { recursive: true });
    var outputPath = path.join(outputDir, "haskell.json");
    fs.writeFileSync(outputPath, JSON.stringify(components, null, 2), "utf-8");
    console.log("Successfully extracted components to ".concat(outputPath));
}
main();
