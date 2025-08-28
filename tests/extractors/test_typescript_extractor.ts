import { TypeScriptComponentExtractor } from '../../codetraverse/extractors/typescript_extractor';
import * as fs from 'fs';
import * as path from 'path';

describe('TypeScriptComponentExtractor', () => {
    it('should extract components from a simple TypeScript file', () => {
        const extractor = new TypeScriptComponentExtractor();
        const sampleFilePath = path.join(__dirname, '..', '..', 'sample_code_repo_test', 'typescript', 'index.ts');
        extractor.processFile(sampleFilePath);
        const components = extractor.extractAllComponents();
        expect(components.length).toBeGreaterThan(0);
    });
});
