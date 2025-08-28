export interface ComponentExtractor {
  processFile(filePath: string): void;
  writeToFile(outputPath: string): void;
  extractAllComponents(): any[];
}
