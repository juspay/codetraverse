import { CodeTraverseBridge } from '../bridge';
import { PythonRunner } from '../python-runner';
import { InvalidLanguageError, FileNotFoundError } from '../types';

// Mock the PythonRunner
jest.mock('../python-runner');

const MockPythonRunner = PythonRunner as jest.MockedClass<typeof PythonRunner>;

describe('CodeTraverseBridge', () => {
  let bridge: CodeTraverseBridge;
  let mockRunner: jest.Mocked<PythonRunner>;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Create a mock instance
    mockRunner = {
      runSingleFileAnalysis: jest.fn(),
      runSchemaExtraction: jest.fn(), 
      runAnalysis: jest.fn(),
      runPathQuery: jest.fn(),
      validateSetup: jest.fn(),
      ensureOutputDirectories: jest.fn(),
      getAbsolutePath: jest.fn(),
    } as any;

    MockPythonRunner.mockImplementation(() => mockRunner);
    
    bridge = new CodeTraverseBridge();
  });

  describe('constructor', () => {
    it('should create a bridge with default config', () => {
      expect(MockPythonRunner).toHaveBeenCalledWith({});
    });

    it('should create a bridge with custom config', () => {
      const config = { pythonPath: 'python3', timeout: 30000 };
      new CodeTraverseBridge(config);
      expect(MockPythonRunner).toHaveBeenCalledWith(config);
    });
  });

  describe('analyzeFile', () => {
    it('should analyze a single file successfully', async () => {
      const mockComponents = [
        {
          kind: 'function' as const,
          name: 'testFunction',
          module: 'test',
          start_line: 1,
          end_line: 5,
          full_component_path: 'test::testFunction',
          parameters: [],
          type_signature: null,
          function_calls: []
        }
      ];

      mockRunner.runSingleFileAnalysis.mockResolvedValue({
        stdout: JSON.stringify(mockComponents),
        stderr: ''
      });

      const result = await bridge.analyzeFile('/path/to/file.ts', 'typescript');

      expect(mockRunner.runSingleFileAnalysis).toHaveBeenCalledWith('/path/to/file.ts', 'typescript');
      expect(result).toEqual(mockComponents);
    });

    it('should throw InvalidLanguageError for unsupported language', async () => {
      await expect(
        bridge.analyzeFile('/path/to/file.xyz', 'unsupported' as any)
      ).rejects.toThrow(InvalidLanguageError);

      expect(mockRunner.runSingleFileAnalysis).not.toHaveBeenCalled();
    });

    it('should handle JSON parse errors', async () => {
      mockRunner.runSingleFileAnalysis.mockResolvedValue({
        stdout: 'invalid json',
        stderr: ''
      });

      await expect(
        bridge.analyzeFile('/path/to/file.ts', 'typescript')
      ).rejects.toThrow();
    });
  });

  describe('analyzeWorkspace', () => {
    it('should analyze workspace successfully', async () => {
      const mockSchema = {
        nodes: [{ id: 'test::func', category: 'function', location: { module: 'test', start_line: 1, end_line: 5 } }],
        edges: [{ from: 'test::func', to: 'test::other', relation: 'calls' }]
      };

      mockRunner.runSchemaExtraction.mockResolvedValue({
        stdout: JSON.stringify(mockSchema),
        stderr: ''
      });

      const result = await bridge.analyzeWorkspace('/path/to/project', {
        language: 'typescript'
      });

      expect(mockRunner.runSchemaExtraction).toHaveBeenCalledWith(
        '/path/to/project',
        'typescript',
        'fdep',
        'graph'
      );
      expect(result).toEqual(mockSchema);
    });

    it('should use custom output directories', async () => {
      mockRunner.runSchemaExtraction.mockResolvedValue({
        stdout: JSON.stringify({ nodes: [], edges: [] }),
        stderr: ''
      });

      await bridge.analyzeWorkspace('/path/to/project', {
        language: 'python',
        outputBase: 'custom_fdep',
        graphDir: 'custom_graph'
      });

      expect(mockRunner.runSchemaExtraction).toHaveBeenCalledWith(
        '/path/to/project',
        'python',
        'custom_fdep',
        'custom_graph'
      );
    });
  });

  describe('findPath', () => {
    it('should find path between components', async () => {
      const mockOutput = 'Shortest path from \'A\' → \'B\':\n  A → B';
      
      mockRunner.runPathQuery.mockResolvedValue({
        stdout: mockOutput,
        stderr: ''
      });

      const result = await bridge.findPath('/path/to/graph.graphml', 'A', 'B');

      expect(mockRunner.runPathQuery).toHaveBeenCalledWith('/path/to/graph.graphml', 'B', 'A');
      expect(result.found).toBe(true);
      expect(result.path).toEqual(['A', 'B']);
    });

    it('should handle no path found', async () => {
      mockRunner.runPathQuery.mockResolvedValue({
        stdout: 'No path found',
        stderr: ''
      });

      const result = await bridge.findPath('/path/to/graph.graphml', 'B', 'A');

      expect(result.found).toBe(false);
      expect(result.path).toBeUndefined();
    });
  });

  describe('getNeighbors', () => {
    it('should get component neighbors', async () => {
      const mockOutput = `Nodes with edges INTO 'component' (1):
  A --[calls]--> component
  
Nodes with edges OUT OF 'component' (1):
  component --[uses]--> B`;

      mockRunner.runPathQuery.mockResolvedValue({
        stdout: mockOutput,
        stderr: ''
      });

      const result = await bridge.getNeighbors('/path/to/graph.graphml', 'component');

      expect(result.incoming).toEqual([{ from: 'A', relation: 'calls' }]);
      expect(result.outgoing).toEqual([{ to: 'B', relation: 'uses' }]);
    });
  });

  describe('validateSetup', () => {
    it('should validate setup successfully', async () => {
      mockRunner.validateSetup.mockResolvedValue();

      await expect(bridge.validateSetup()).resolves.not.toThrow();
      expect(mockRunner.validateSetup).toHaveBeenCalled();
    });

    it('should propagate validation errors', async () => {
      const error = new Error('Python not found');
      mockRunner.validateSetup.mockRejectedValue(error);

      await expect(bridge.validateSetup()).rejects.toThrow('Python not found');
    });
  });

  describe('language support', () => {
    it('should return supported languages', () => {
      const languages = bridge.getSupportedLanguages();
      expect(languages).toEqual(['haskell', 'python', 'rescript', 'typescript', 'rust', 'golang']);
    });

    it('should check if language is supported', () => {
      expect(bridge.isLanguageSupported('typescript')).toBe(true);
      expect(bridge.isLanguageSupported('javascript')).toBe(false);
    });
  });
});