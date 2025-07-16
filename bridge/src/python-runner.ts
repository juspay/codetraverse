import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import {
  BridgeConfig,
  PythonProcessError,
  ShellScriptError,
  FileNotFoundError,
  Language
} from './types';

/**
 * Utility class for spawning and managing Python processes
 */
export class PythonRunner {
  private readonly pythonPath: string;
  private readonly codetraversePath: string;
  private readonly timeout: number;
  private readonly workingDirectory: string;

  constructor(config: BridgeConfig = {}) {
    this.pythonPath = config.pythonPath || 'python';
    this.codetraversePath = config.codetraversePath || 'codetraverse';
    this.timeout = config.timeout || 60000; // 60 seconds default
    this.workingDirectory = config.workingDirectory || process.cwd();
  }

  async createEnv() {
    console.log(this.pythonPath, this.codetraversePath)
    await this.executeShell([path.join(this.codetraversePath, "scripts/setup.sh"), this.pythonPath, this.codetraversePath])
  }

  /**
   * Execute the main codetraverse analysis
   */
  async runAnalysis(
    rootDir: string,
    language: Language,
    outputBase?: string,
    graphDir?: string
  ): Promise<{ stdout: string; stderr: string }> {
    await this.validatePath(rootDir);

    const args = [
      '-m', "codetraverse.utils.blackbox",
      '--ROOT_DIR', rootDir,
      '--LANGUAGE', language
    ];

    if (outputBase) {
      args.push('--OUTPUT_BASE', outputBase);
    }

    if (graphDir) {
      args.push('--GRAPH_DIR', graphDir);
    }

    return this.executeCommand(args);
  }

  /**
   * Execute path finding between components
   */
  async runPathQuery(
    graphPath: string,
    component: string,
    source?: string
  ): Promise<{ stdout: string; stderr: string }> {
    await this.validatePath(graphPath);
    let args: string[];
    if (source) {
      args = ["python", "-c", `import codetraverse.path as codepath;codepath.find_path(\"${graphPath}\", \"${component}\", \"${source}\")`]
    } else {
      args = ["python", "-c", `import codetraverse.path as codepath;codepath.find_path(\"${graphPath}\", \"${component}\")`]
    }

    return this.executeCommand(args);
  }

  /**
   * Execute a single file analysis using enhanced Python CLI
   */
  async runSingleFileAnalysis(
    filePath: string,
    language: Language,
    outputFormat: 'json' = 'json'
  ): Promise<{ stdout: string; stderr: string }> {
    await this.validatePath(filePath);

    const args = [
      '-m', "codetraverse.utils.blackbox",
      '--SINGLE_FILE', filePath,
      '--LANGUAGE', language,
      '--OUTPUT_FORMAT', outputFormat,
      '--QUIET'  // Suppress progress output for single files
    ];

    return this.executeCommand(args);
  }

  /**
   * Get unified schema as JSON from workspace analysis
   */
  async runSchemaExtraction(
    rootDir: string,
    language: Language,
    outputBase?: string,
    graphDir?: string
  ): Promise<{ stdout: string; stderr: string }> {
    await this.validatePath(rootDir);

    const args = [
      '-m', "codetraverse.utils.blackbox",
      '--ROOT_DIR', rootDir,
      '--LANGUAGE', language,
      '--JSON_SCHEMA',
      '--QUIET'
    ];

    if (outputBase) {
      args.push('--OUTPUT_BASE', outputBase);
    }

    if (graphDir) {
      args.push('--GRAPH_DIR', graphDir);
    }

    return this.executeCommand(args);
  }

  async runBlackbox(
    fn: string,
    args: string[]
  ): Promise<{ stdout: string; stderr: string }> {
    const cmd = ["-m", "codetraverse.utils.blackbox", fn, ...args];
    return this.executeCommand(cmd);
  }

  async runCreateFdepDataAndGraph(
    rootDir: string,
    outputBase: string,
    graphDir: string,
    noClear: boolean
  ): Promise<{ stdout: string; stderr: string }> {
    const args = [
      'create_fdep_data',
      rootDir,
      '--output_base', outputBase,
      '--graph_dir', graphDir
    ];
    if (noClear) {
      args.push('--no_clear');
    }
    // Use the main.py entrypoint instead of utils.blackbox
    const cmd = ['-m', "codetraverse.main", ...args];
    return this.executeCommand(cmd, -1);
  }

  /**
   * Execute the AST diff orchestrator
   */
  async runAstDiff(
    config: object
  ): Promise<{ stdout: string; stderr: string }> {
    const configJson = JSON.stringify(config);
    const args = [
      '-m', 'codetraverse.utils.AstDifferOrchestrator',
      '--config-json', configJson
    ];
    return this.executeCommand(args);
  }

  /**
   * Check if Python and codetraverse are available
   */
  async validateSetup(): Promise<void> {
    try {
      // Check Python
      await this.executeCommand(['--version'], 5000);

      // Check codetraverse module
      await this.executeCommand(['-m', "codetraverse.utils.blackbox", '--help'], 10000);
    } catch (error) {
      if (error instanceof PythonProcessError) {
        throw new PythonProcessError(
          `CodeTraverse setup validation failed: ${error.message}`,
          error.exitCode,
          error.stderr
        );
      }
      throw error;
    }
  }

  private async executeShell(
    args: string[]
  ): Promise<{ stdout: string, stderr: string }> {
    return new Promise((resolve, reject) => {
      const actualTimeout = 5 * 60 * 1000;
      let stdout = '';
      let stderr = '';

      const child: ChildProcess = spawn("sh", args, {
        cwd: this.workingDirectory,
        stdio: ['pipe', 'pipe', 'pipe'],
        shell: true
      });

      // Set up timeout
      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new ShellScriptError(
          `Python process timed out after ${actualTimeout}ms`,
          -1,
          'Process timeout'
        ));
      }, actualTimeout);

      // Collect stdout
      child.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString();
      });

      // Collect stderr
      child.stderr?.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      // Handle process completion
      child.on('close', (code: number | null) => {
        clearTimeout(timer);

        if (code === 0) {
          resolve({ stdout: stdout.trim(), stderr: stderr.trim() });
        } else {
          reject(new ShellScriptError(
            `shell script exited with code ${code || 'unknown'}`,
            code || -1,
            stderr.trim()
          ));
        }
      });

      // Handle process errors
      child.on('error', (error: Error) => {
        clearTimeout(timer);
        reject(new ShellScriptError(
          `Failed to spawn Python process: ${error.message}`,
          -1,
          error.message
        ));
      });
    });
  }

  /**
   * Execute a Python command with proper error handling
   */
  private async executeCommand(
    args: string[],
    timeoutMs?: number
  ): Promise<{ stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      const actualTimeout = timeoutMs || this.timeout;
      let stdout = '';
      let stderr = '';
      const uvPath = path.join(process.env.HOME || "./", "npm_codetraverse", "tmp_env", "bin", "uv")
      const child: ChildProcess = spawn(uvPath, ["run", ...args], {
        cwd: this.codetraversePath,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
          ...process.env,
          VIRTUAL_ENV: path.join(process.env.HOME || "./", "npm_codetraverse", ".venv"),
        }
      });

      // Set up timeout
      let timer = undefined;
      if (timeoutMs != -1) {
        const timer = setTimeout(() => {
          child.kill('SIGKILL');
          reject(new PythonProcessError(
            `Python process timed out after ${actualTimeout}ms`,
            -1,
            'Process timeout'
          ));
        }, actualTimeout);
      }

      // Collect stdout
      child.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString();
      });

      // Collect stderr
      child.stderr?.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      // Handle process completion
      child.on('close', (code: number | null) => {
        if (timeoutMs != -1) {
          clearTimeout(timer);
        }

        if (code === 0) {
          resolve({ stdout: stdout.trim(), stderr: stderr.trim() });
        } else {
          reject(new PythonProcessError(
            `Python process exited with code ${code || 'unknown'}`,
            code || -1,
            stderr.trim()
          ));
        }
      });

      // Handle process errors
      child.on('error', (error: Error) => {
        clearTimeout(timer);
        reject(new PythonProcessError(
          `Failed to spawn Python process: ${error.message}`,
          -1,
          error.message
        ));
      });
    });
  }

  /**
   * Validate that a file or directory path exists
   */
  private async validatePath(filePath: string): Promise<void> {
    try {
      await fs.promises.access(filePath, fs.constants.F_OK);
    } catch {
      throw new FileNotFoundError(filePath);
    }
  }

  /**
   * Get the absolute path for a given relative path
   */
  getAbsolutePath(relativePath: string): string {
    if (path.isAbsolute(relativePath)) {
      return relativePath;
    }
    return path.resolve(this.workingDirectory, relativePath);
  }

  /**
   * Create output directories if they don't exist
   */
  async ensureOutputDirectories(outputBase: string, graphDir: string): Promise<void> {
    const dirs = [
      this.getAbsolutePath(outputBase),
      this.getAbsolutePath(graphDir)
    ];

    for (const dir of dirs) {
      try {
        await fs.promises.mkdir(dir, { recursive: true });
      } catch (error) {
        if (error instanceof Error) {
          throw new PythonProcessError(
            `Failed to create output directory ${dir}: ${error.message}`,
            -1,
            error.message
          );
        }
        throw error;
      }
    }
  }
}