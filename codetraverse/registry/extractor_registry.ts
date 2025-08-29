import { HaskellComponentExtractor } from '../extractors/haskell_extractor';
import { PythonComponentExtractor } from '../extractors/python_extractor';
import { RustComponentExtractor } from '../extractors/rust_extractor';
import { TypeScriptComponentExtractor } from '../extractors/typescript_extractor';
// Import other extractors here

const extractorMap: Record<string, any> = {
    "haskell": HaskellComponentExtractor,
    "python": PythonComponentExtractor,
    // "rescript": RescriptComponentExtractor,
    "rust": RustComponentExtractor,
    // "golang": GoComponentExtractor,
    "typescript": TypeScriptComponentExtractor,
    // "purescript": PurescriptComponentExtractor,
    // "javascript": JavascriptComponentExtractor
};

export function getExtractor(language: string) {
    const extractor = extractorMap[language];
    if (!extractor) {
        throw new Error(`No extractor found for language: ${language}`);
    }
    return new extractor();
}
