"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const haskell_extractor_1 = require("./extractors/haskell_extractor");
const typescript_extractor_1 = require("./extractors/typescript_extractor");
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
    function walk(dir) {
        const files = fs.readdirSync(dir);
        for (const file of files) {
            const fullPath = path.join(dir, file);
            if (fs.statSync(fullPath).isDirectory()) {
                walk(fullPath);
            }
            else if (path.extname(fullPath) === ".hs" || path.extname(fullPath) === ".ts") {
                try {
                    const fileContent = fs.readFileSync(fullPath, "utf-8");
                    if (fileContent.trim().length === 0) {
                        console.log(`Skipping empty file: ${fullPath}`);
                        continue;
                    }
                    console.log(`Processing ${fullPath}`);
                    let extractor;
                    if (path.extname(fullPath) === ".hs") {
                        extractor = new haskell_extractor_1.HaskellComponentExtractor();
                    }
                    else {
                        extractor = new typescript_extractor_1.TypeScriptComponentExtractor();
                    }
                    extractor.processFile(fullPath);
                    const components = extractor.extractAllComponents();
                    const relativePath = path.relative(repoPath, fullPath);
                    const outputDirPath = path.join(outputDir, path.dirname(relativePath));
                    fs.mkdirSync(outputDirPath, { recursive: true });
                    const outputFileName = path.basename(relativePath) + ".json";
                    const outputPath = path.join(outputDirPath, outputFileName);
                    fs.writeFileSync(outputPath, JSON.stringify(components, null, 2), "utf-8");
                    console.log(`Successfully extracted components to ${outputPath}`);
                }
                catch (e) {
                    console.error(`Error processing file ${fullPath}:`, e.message);
                }
            }
        }
    }
    walk(repoPath);
}
main();
//# sourceMappingURL=testing.js.map