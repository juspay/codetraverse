import { PythonRunner } from '../python-runner';
import { PythonProcessError, FileNotFoundError } from '../types';
import * as fs from 'fs';
import { spawn } from 'child_process';

// Mock child_process and fs
jest.mock('child_process');
jest.mock('fs', () => ({
  promises: {
    access: jest.fn(),
    mkdir: jest.fn(),
  },
  constants: {
    F_OK: 0,
  },
}));

const mockSpawn = spawn as jest.MockedFunction<typeof spawn>;
const mockFsAccess = fs.promises.access as jest.MockedFunction<typeof fs.promises.access>;
const mockFsMkdir = fs.promises.mkdir as jest.MockedFunction<typeof fs.promises.mkdir>;

describe('PythonRunner', () => {
  let runner: PythonRunner;

  beforeEach(() => {
    jest.clearAllMocks();
    runner = new PythonRunner();
  });

  describe('constructor', () => {
    it('should create runner with default config', () => {
      const defaultRunner = new PythonRunner();
      expect(defaultRunner).toBeInstanceOf(PythonRunner);
    });

    it('should create runner with custom config', () => {
      const customRunner = new PythonRunner({
        pythonPath: 'python3',
        codetraversePath: 'custom-codetraverse',
        timeout: 30000,
        workingDirectory: '/custom/dir'
      });
      expect(customRunner).toBeInstanceOf(PythonRunner);
    });
  });

  describe('runAnalysis', () => {
    it('should run analysis successfully', async () => {
      const mockChild = createMockChildProcess();
      mockSpawn.mockReturnValue(mockChild);
      mockFsAccess.mockResolvedValue();

      // Simulate successful process
      process.nextTick(() => {
        mockChild.emit('close', 0);
      });

      const result = await runner.runAnalysis('/test/dir', 'typescript');

      expect(mockSpawn).toHaveBeenCalledWith('python', [
        '-m', 'codetraverse',
        '--ROOT_DIR', '/test/dir',
        '--LANGUAGE', 'typescript'
      ], expect.any(Object));

      expect(result.stdout).toBe('test output');
      expect(result.stderr).toBe('test error');
    });

    it('should handle file not found', async () => {
      mockFsAccess.mockRejectedValue(new Error('ENOENT'));

      await expect(
        runner.runAnalysis('/nonexistent', 'typescript')
      ).rejects.toThrow(FileNotFoundError);
    });

    it('should handle process error', async () => {
      const mockChild = createMockChildProcess();
      mockSpawn.mockReturnValue(mockChild);
      mockFsAccess.mockResolvedValue();

      process.nextTick(() => {
        mockChild.emit('close', 1);
      });

      await expect(
        runner.runAnalysis('/test/dir', 'typescript')
      ).rejects.toThrow(PythonProcessError);
    });

    it('should handle spawn error', async () => {
      const mockChild = createMockChildProcess();
      mockSpawn.mockReturnValue(mockChild);
      mockFsAccess.mockResolvedValue();

      process.nextTick(() => {
        mockChild.emit('error', new Error('spawn failed'));
      });

      await expect(
        runner.runAnalysis('/test/dir', 'typescript')
      ).rejects.toThrow(PythonProcessError);
    });

    it('should handle timeout', async () => {
      const mockChild = createMockChildProcess();
      mockChild.kill = jest.fn();
      mockSpawn.mockReturnValue(mockChild);
      mockFsAccess.mockResolvedValue();

      const shortTimeoutRunner = new PythonRunner({ timeout: 10 });

      // Don't emit close event to simulate hanging process
      const promise = shortTimeoutRunner.runAnalysis('/test/dir', 'typescript');

      await expect(promise).rejects.toThrow('Python process timed out');
      expect(mockChild.kill).toHaveBeenCalledWith('SIGKILL');
    }, 100);
  });

  describe('runSingleFileAnalysis', () => {
    it('should run single file analysis', async () => {
      const mockChild = createMockChildProcess();
      mockSpawn.mockReturnValue(mockChild);
      mockFsAccess.mockResolvedValue();

      process.nextTick(() => {
        mockChild.emit('close', 0);
      });

      await runner.runSingleFileAnalysis('/test/file.ts', 'typescript');

      expect(mockSpawn).toHaveBeenCalledWith('python', [
        '-m', 'codetraverse',
        '--SINGLE_FILE', '/test/file.ts',
        '--LANGUAGE', 'typescript',
        '--OUTPUT_FORMAT', 'json',
        '--QUIET'
      ], expect.any(Object));
    });
  });

  describe('runSchemaExtraction', () => {
    it('should run schema extraction', async () => {
      const mockChild = createMockChildProcess();
      mockSpawn.mockReturnValue(mockChild);
      mockFsAccess.mockResolvedValue();

      process.nextTick(() => {
        mockChild.emit('close', 0);
      });

      await runner.runSchemaExtraction('/test/dir', 'python', 'output', 'graphs');

      expect(mockSpawn).toHaveBeenCalledWith('python', [
        '-m', 'codetraverse',
        '--ROOT_DIR', '/test/dir',
        '--LANGUAGE', 'python',
        '--JSON_SCHEMA',
        '--QUIET',
        '--OUTPUT_BASE', 'output',
        '--GRAPH_DIR', 'graphs'
      ], expect.any(Object));
    });
  });

  describe('runPathQuery', () => {
    it('should run path query', async () => {
      const mockChild = createMockChildProcess();
      mockSpawn.mockReturnValue(mockChild);
      mockFsAccess.mockResolvedValue();

      process.nextTick(() => {
        mockChild.emit('close', 0);
      });

      await runner.runPathQuery('/test/graph.graphml', 'component', 'source');

      expect(mockSpawn).toHaveBeenCalledWith('python', [
        'codetraverse/path.py',
        '--GRAPH_PATH', '/test/graph.graphml',
        '--COMPONENT', 'component',
        '--SOURCE', 'source'
      ], expect.any(Object));
    });
  });

  describe('ensureOutputDirectories', () => {
    it('should create output directories', async () => {
      mockFsMkdir.mockResolvedValue(undefined);

      await runner.ensureOutputDirectories('output', 'graphs');

      expect(mockFsMkdir).toHaveBeenCalledTimes(2);
      expect(mockFsMkdir).toHaveBeenCalledWith(expect.stringContaining('output'), { recursive: true });
      expect(mockFsMkdir).toHaveBeenCalledWith(expect.stringContaining('graphs'), { recursive: true });
    });

    it('should handle mkdir errors', async () => {
      mockFsMkdir.mockRejectedValue(new Error('Permission denied'));

      await expect(
        runner.ensureOutputDirectories('output', 'graphs')
      ).rejects.toThrow(PythonProcessError);
    });
  });

  describe('getAbsolutePath', () => {
    it('should return absolute path for relative input', () => {
      const result = runner.getAbsolutePath('relative/path');
      expect(result).toMatch(/.*relative\/path$/);
    });

    it('should return absolute path unchanged', () => {
      const absolutePath = '/absolute/path';
      const result = runner.getAbsolutePath(absolutePath);
      expect(result).toBe(absolutePath);
    });
  });
});

// Helper function to create mock child process
function createMockChildProcess() {
  const mockChild: any = {
    stdout: {
      on: jest.fn((event, callback) => {
        if (event === 'data') {
          process.nextTick(() => callback(Buffer.from('test output')));
        }
      }),
    },
    stderr: {
      on: jest.fn((event, callback) => {
        if (event === 'data') {
          process.nextTick(() => callback(Buffer.from('test error')));
        }
      }),
    },
    on: jest.fn((event, callback) => {
      if (event === 'close') {
        // Store the callback to call later
        mockChild._closeCallback = callback;
      } else if (event === 'error') {
        mockChild._errorCallback = callback;
      }
    }),
    emit: jest.fn((event, ...args) => {
      if (event === 'close' && mockChild._closeCallback) {
        process.nextTick(() => mockChild._closeCallback(...args));
      } else if (event === 'error' && mockChild._errorCallback) {
        process.nextTick(() => mockChild._errorCallback(...args));
      }
    }),
    kill: jest.fn(),
    _closeCallback: null,
    _errorCallback: null,
  };

  return mockChild;
}