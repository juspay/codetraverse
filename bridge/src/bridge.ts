import * as path from 'path';
import * as fs from 'fs';
import {
  BridgeConfig,
  AnalysisOptions,
  Component,
  GraphData,
  PathResult,
  ChildInfo,
  ParentInfo,
  CommonParentInfo,
  CommonChildInfo,
  NeighborResult,
  Language,
  CodeTraverseError,
  InvalidLanguageError
} from './types';
import { PythonRunner } from './python-runner';

/**
 * Main bridge class providing a TypeScript/Node.js API for CodeTraverse
 */
export class CodeTraverseBridge {
  private readonly runner: PythonRunner;
  private readonly supportedLanguages: Language[] = [
    'haskell', 'python', 'rescript', 'typescript', 'rust', 'golang'
  ];

  constructor(config: BridgeConfig = {}) {
    this.runner = new PythonRunner(config);
  }

  async createEnv() {
    await this.runner.createEnv();
  }

  /**
   * Analyze a single file and return extracted components
   */
  async analyzeFile(filePath: string, language: Language): Promise<Component[]> {
    this.validateLanguage(language);

    try {
      const result = await this.runner.runSingleFileAnalysis(filePath, language);
      return JSON.parse(result.stdout) as Component[];
    } catch (error) {
      throw this.wrapError(error, 'analyzeFile');
    }
  }

  /**
   * Analyze an entire workspace/repository and return graph data
   */
  async analyzeWorkspace(rootPath: string, options: AnalysisOptions): Promise<GraphData> {
    this.validateLanguage(options.language);

    try {
      const outputBase = options.outputBase || 'fdep';
      const graphDir = options.graphDir || 'graph';

      // Use the JSON schema extraction method for faster processing
      const result = await this.runner.runSchemaExtraction(
        rootPath,
        options.language,
        outputBase,
        graphDir
      );

      // Parse the unified schema from stdout
      const schema = JSON.parse(result.stdout) as GraphData;
      return schema;
    } catch (error) {
      throw this.wrapError(error, 'analyzeWorkspace');
    }
  }

  /**
   * Analyze workspace and return raw components (without building graph)
   */
  async analyzeWorkspaceComponents(
    rootPath: string,
    options: AnalysisOptions
  ): Promise<Component[]> {
    this.validateLanguage(options.language);

    try {
      const outputBase = options.outputBase || 'fdep';
      const graphDir = options.graphDir || 'graph';

      // Ensure output directories exist
      await this.runner.ensureOutputDirectories(outputBase, graphDir);

      // Run the analysis
      await this.runner.runAnalysis(
        rootPath,
        options.language,
        outputBase,
        graphDir
      );

      // Load components from JSON files
      return await this.loadComponentsFromDirectory(outputBase);
    } catch (error) {
      throw this.wrapError(error, 'analyzeWorkspaceComponents');
    }
  }

  /**
   * Find the shortest path between two components in a graph
   */
  async findPath(
    graphPath: string,
    fromComponent: string,
    toComponent: string
  ): Promise<PathResult> {
    try {
      const result = await this.runner.runPathQuery(graphPath, toComponent, fromComponent);
      return this.parsePathResult(result.stdout);
    } catch (error) {
      throw this.wrapError(error, 'findPath');
    }
  }

  /**
   * Get direct neighbors (incoming and outgoing edges) for a component
   */
  async getNeighbors(graphPath: string, component: string): Promise<NeighborResult> {
    try {
      const result = await this.runner.runPathQuery(graphPath, component);
      return this.parseNeighborResult(result.stdout);
    } catch (error) {
      throw this.wrapError(error, 'getNeighbors');
    }
  }

  /**
   * Validate that the bridge setup is working correctly
   */
  async validateSetup(): Promise<void> {
    try {
      await this.runner.validateSetup();
    } catch (error) {
      throw this.wrapError(error, 'validateSetup');
    }
  }

  /**
   * Get the all the components a module is exporting
   */
  async getModuleInfo(
    fdepFolder: string,
    moduleName: string
  ): Promise<Component[]> {
    const { stdout } = await this.runner.runBlackbox('getModuleInfo', [fdepFolder, moduleName]);
    return JSON.parse(stdout) as Component[];
  }

  /**
   * get the json output of a particular component
   */
  async getFunctionInfo(
    fdepFolder: string,
    componentName: string,
    componentType = 'function'
  ): Promise<Component[]> {
    const { stdout } = await this.runner.runBlackbox('getFunctionInfo', [fdepFolder, componentName, '--component_type', componentType]);
    return JSON.parse(stdout) as Component[];
  }

  /**
   * get the children of a component based on the depth provided
   */
  async getFunctionChildren(
    graphPath: string,
    moduleName: string,
    componentName: string,
    depth = 1
  ): Promise<ChildInfo[]> {
    const { stdout } = await this.runner.runBlackbox('getFunctionChildren', [graphPath, moduleName, componentName, '--depth', depth.toString()]);
    return JSON.parse(stdout) as ChildInfo[];
  }

  /**
   * get the parents of a component based on the dept provided
   */
  async getFunctionParents(
    graphPath: string,
    moduleName: string,
    componentName: string,
    depth = 1
  ): Promise<ParentInfo[]> {
    const { stdout } = await this.runner.runBlackbox('getFunctionParents', [graphPath, moduleName, componentName, '--depth', depth.toString()]);
    return JSON.parse(stdout) as ParentInfo[];
  }

  /**
   * get the subgraph based on the components and depth provided
   */
  async getSubgraph(
    graphPath: string,
    moduleName: string,
    componentName: string,
    parentDepth = 1,
    childDepth = 1
  ) {
    const { stdout } = await this.runner.runBlackbox('getSubgraph', [graphPath, moduleName, componentName, '--parent_depth', parentDepth.toString(), '--child_depth', childDepth.toString()]);
    return JSON.parse(stdout) as GraphData;
  }

  /**
   * get the common parents of two components
   */
  async getCommonParents(
    graphPath: string,
    moduleName1: string,
    componentName1: string,
    moduleName2: string,
    componentName2: string
  ): Promise<CommonParentInfo[]> {
    const { stdout } = await this.runner.runBlackbox('getCommonParents', [graphPath, moduleName1, componentName1, moduleName2, componentName2]);
    return JSON.parse(stdout) as CommonParentInfo[];
  }

  /**
   * get the common children of two components
   */
  async getCommonChildren(
    graphPath: string,
    moduleName1: string,
    componentName1: string,
    moduleName2: string,
    componentName2: string
  ): Promise<CommonChildInfo[]> {
    const { stdout } = await this.runner.runBlackbox('getCommonChildren', [graphPath, moduleName1, componentName1, moduleName2, componentName2]);
    return JSON.parse(stdout) as CommonChildInfo[];
  }

  /**
   * Get list of supported languages
   */
  getSupportedLanguages(): Language[] {
    return [...this.supportedLanguages];
  }

  /**
   * Check if a language is supported
   */
  isLanguageSupported(language: string): language is Language {
    return this.supportedLanguages.includes(language as Language);
  }

  /**
   * Load graph data from a GraphML file
   * Note: This is a simplified implementation. In practice, you might want to use
   * a proper GraphML parser or convert to JSON format from Python.
   */
  private async loadGraphFromFile(graphPath: string): Promise<GraphData> {
    try {
      // For now, we'll throw an error suggesting to implement GraphML parsing
      // In a real implementation, you'd either:
      // 1. Use a GraphML parsing library
      // 2. Modify Python to also output JSON format
      // 3. Use a lightweight XML parser

      throw new CodeTraverseError(
        'GraphML parsing not yet implemented. Consider using analyzeWorkspaceComponents() for raw component data.',
        'GRAPHML_PARSING_NOT_IMPLEMENTED'
      );
    } catch (error) {
      throw this.wrapError(error, 'loadGraphFromFile');
    }
  }

  /**
   * Load components from JSON files in a directory
   */
  private async loadComponentsFromDirectory(outputBase: string): Promise<Component[]> {
    const components: Component[] = [];

    try {
      const files = await this.getJsonFiles(outputBase);

      for (const file of files) {
        const content = await fs.promises.readFile(file, 'utf-8');
        const fileComponents = JSON.parse(content) as Component[];
        components.push(...fileComponents);
      }

      return components;
    } catch (error) {
      throw this.wrapError(error, 'loadComponentsFromDirectory');
    }
  }

  /**
   * Recursively find all JSON files in a directory
   */
  private async getJsonFiles(dir: string): Promise<string[]> {
    const files: string[] = [];

    const entries = await fs.promises.readdir(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);

      if (entry.isDirectory()) {
        const subFiles = await this.getJsonFiles(fullPath);
        files.push(...subFiles);
      } else if (entry.isFile() && entry.name.endsWith('.json')) {
        files.push(fullPath);
      }
    }

    return files;
  }

  /**
   * Parse path finding result from Python output
   */
  private parsePathResult(stdout: string): PathResult {
    const lines = stdout.trim().split('\n');

    // Look for path output pattern
    const pathLine = lines.find(line => line.includes('→'));

    if (pathLine) {
      // Extract path from line like: "PgIntegrationApp::init → PgIntegrationApp::process → PgIntegrationApp::make"
      const parts = pathLine.split('→').map(part => part.trim());
      const pathMatch = parts.length > 1 ? parts : null;

      return {
        found: true,
        path: pathMatch || [],
        message: stdout
      };
    }

    return {
      found: false,
      message: stdout
    };
  }

  /**
   * Parse neighbor discovery result from Python output
   */
  private parseNeighborResult(stdout: string): NeighborResult {
    const lines = stdout.trim().split('\n');
    const incoming: Array<{ from: string; relation: string }> = [];
    const outgoing: Array<{ to: string; relation: string }> = [];

    let section: 'incoming' | 'outgoing' | null = null;

    for (const line of lines) {
      if (line.includes('edges INTO')) {
        section = 'incoming';
        continue;
      } else if (line.includes('edges OUT OF')) {
        section = 'outgoing';
        continue;
      }

      // Parse edge lines like: "PgIntegrationApp::process --[calls]--> PgIntegrationApp::make"
      const edgeMatch = line.match(/(.+?)\s+--\[(.+?)\]-->\s+(.+)/);
      if (edgeMatch && section) {
        const [, from, relation, to] = edgeMatch;

        if (section === 'incoming' && from && relation) {
          incoming.push({ from: from.trim(), relation: relation.trim() });
        } else if (section === 'outgoing' && to && relation) {
          outgoing.push({ to: to.trim(), relation: relation.trim() });
        }
      }
    }

    return { incoming, outgoing };
  }

  /**
   * Validate that a language is supported
   */
  private validateLanguage(language: Language): void {
    if (!this.isLanguageSupported(language)) {
      throw new InvalidLanguageError(language);
    }
  }

  /**
   * Wrap errors with additional context
   */
  private wrapError(error: unknown, operation: string): Error {
    if (error instanceof Error) {
      return error;
    }
    return new CodeTraverseError(
      `Unknown error in ${operation}: ${String(error)}`,
      'UNKNOWN_ERROR',
      error
    );
  }
}

// new CodeTraverseBridge({pythonPath: "/usr/local/bin/python3.10", codetraversePath: "./"}).createEnv()