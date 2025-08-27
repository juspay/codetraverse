import { spawn, ChildProcess } from 'child_process';
import { Worker, isMainThread, parentPort, workerData } from 'worker_threads';
import * as path from 'path';
import * as fs from 'fs';
import {
  BridgeConfig,
  PythonProcessError,
  ShellScriptError,
  FileNotFoundError,
  Language
} from './types';
import { logToFile } from './logger';

// Memory tracking utilities
export interface MemorySnapshot {
  timestamp: number;
  nodeMemory: NodeJS.MemoryUsage;
  processId: number;
  workerCount: number;
  availableWorkers: number;
  queuedTasks: number;
}

class MemoryTracker {
  private snapshots: MemorySnapshot[] = [];
  private trackingEnabled: boolean = false;
  private intervalId: NodeJS.Timeout | null = null;
  private readonly maxSnapshots: number = 100;

  startTracking(intervalMs: number = 30000): void {
    this.trackingEnabled = true;
    this.snapshots = [];
    
    logToFile.info(`[MemoryTracker] Starting memory tracking with ${intervalMs}ms intervals`);
    
    // Take initial snapshot
    this.takeSnapshot('tracking_start');
    
    // Set up periodic snapshots
    this.intervalId = setInterval(() => {
      if (this.trackingEnabled) {
        this.takeSnapshot('periodic');
      }
    }, intervalMs);
  }

  stopTracking(): void {
    this.trackingEnabled = false;
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    
    this.takeSnapshot('tracking_stop');
    
    logToFile.info(`[MemoryTracker] Memory tracking stopped. Total snapshots: ${this.snapshots.length}`);
    this.logMemorySummary();
  }

  takeSnapshot(context: string, workerCount: number = 0, availableWorkers: number = 0, queuedTasks: number = 0): MemorySnapshot {
    const memory = process.memoryUsage();
    const snapshot: MemorySnapshot = {
      timestamp: Date.now(),
      nodeMemory: memory,
      processId: process.pid,
      workerCount,
      availableWorkers,
      queuedTasks
    };
    
    // Store snapshot (keep only last N snapshots)
    this.snapshots.push(snapshot);
    if (this.snapshots.length > this.maxSnapshots) {
      this.snapshots.shift();
    }
    
    // Log detailed memory info
    logToFile.debug(`[MemoryTracker] ${context} - Memory snapshot: RSS=${this.formatBytes(memory.rss)}, HeapUsed=${this.formatBytes(memory.heapUsed)}, HeapTotal=${this.formatBytes(memory.heapTotal)}, External=${this.formatBytes(memory.external)}, Workers=${workerCount}, Available=${availableWorkers}, Queued=${queuedTasks}`);
    
    return snapshot;
  }

  logMemoryDelta(beforeSnapshot: MemorySnapshot, afterSnapshot: MemorySnapshot, context: string): void {
    const rssDelta = afterSnapshot.nodeMemory.rss - beforeSnapshot.nodeMemory.rss;
    const heapDelta = afterSnapshot.nodeMemory.heapUsed - beforeSnapshot.nodeMemory.heapUsed;
    const externalDelta = afterSnapshot.nodeMemory.external - beforeSnapshot.nodeMemory.external;
    const timeDelta = afterSnapshot.timestamp - beforeSnapshot.timestamp;
    
    logToFile.info(`[MemoryTracker] ${context} - Memory delta over ${timeDelta}ms: RSS=${this.formatBytesDelta(rssDelta)}, Heap=${this.formatBytesDelta(heapDelta)}, External=${this.formatBytesDelta(externalDelta)}`);
    
    // Log warning for significant memory increases
    if (rssDelta > 50 * 1024 * 1024) { // 50MB threshold
      logToFile.warn(`[MemoryTracker] ${context} - Significant RSS memory increase detected: ${this.formatBytes(rssDelta)}`);
    }
    if (heapDelta > 25 * 1024 * 1024) { // 25MB threshold
      logToFile.warn(`[MemoryTracker] ${context} - Significant heap memory increase detected: ${this.formatBytes(heapDelta)}`);
    }
  }

  private logMemorySummary(): void {
    if (this.snapshots.length < 2) return;
    
    const first = this.snapshots[0];
    const last = this.snapshots[this.snapshots.length - 1];
    
    if (!first || !last) return;
    
    const totalRssDelta = last.nodeMemory.rss - first.nodeMemory.rss;
    const totalHeapDelta = last.nodeMemory.heapUsed - first.nodeMemory.heapUsed;
    const totalTime = last.timestamp - first.timestamp;
    
    logToFile.info(`[MemoryTracker] Session Summary - Duration: ${totalTime}ms, Total RSS Delta: ${this.formatBytesDelta(totalRssDelta)}, Total Heap Delta: ${this.formatBytesDelta(totalHeapDelta)}`);
    
    // Find peak memory usage
    const peakRss = Math.max(...this.snapshots.map(s => s.nodeMemory.rss));
    const peakHeap = Math.max(...this.snapshots.map(s => s.nodeMemory.heapUsed));
    
    logToFile.info(`[MemoryTracker] Peak Usage - RSS: ${this.formatBytes(peakRss)}, Heap: ${this.formatBytes(peakHeap)}`);
  }

  private formatBytes(bytes: number): string {
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = Math.abs(bytes);
    let unitIndex = 0;
    
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    
    const sign = bytes < 0 ? '-' : '';
    return `${sign}${size.toFixed(2)}${units[unitIndex]}`;
  }

  private formatBytesDelta(bytes: number): string {
    const sign = bytes >= 0 ? '+' : '';
    return `${sign}${this.formatBytes(bytes)}`;
  }

  getCurrentMemoryInfo(): string {
    const memory = process.memoryUsage();
    return `RSS=${this.formatBytes(memory.rss)}, Heap=${this.formatBytes(memory.heapUsed)}/${this.formatBytes(memory.heapTotal)}, External=${this.formatBytes(memory.external)}`;
  }

  getSnapshots(): MemorySnapshot[] {
    return [...this.snapshots];
  }
}

// Worker thread implementation
if (!isMainThread && workerData?.isWorker) {
  let currentProcess: ChildProcess | null = null;
  let currentTimer: NodeJS.Timeout | null = null;

  const cleanup = () => {
    logToFile.info(`[Worker ${process.pid}] Starting cleanup procedure`);
    
    if (currentTimer) {
      clearTimeout(currentTimer);
      currentTimer = null;
      logToFile.debug(`[Worker ${process.pid}] Cleared timeout timer`);
    }
    
    if (currentProcess) {
      const pid = currentProcess.pid;
      logToFile.warn(`[Worker ${process.pid}] Killing child process PID: ${pid}`);
      currentProcess.kill('SIGKILL');
      currentProcess = null;
      logToFile.info(`[Worker ${process.pid}] Child process PID: ${pid} killed`);
    } else {
      logToFile.debug(`[Worker ${process.pid}] No active child process to cleanup`);
    }
    
    logToFile.info(`[Worker ${process.pid}] Cleanup procedure completed`);
  };

  const executeCommand = async (data: any) => {
    return new Promise<void>((resolve) => {
      const { commandType, uvPath, uvCommand, args, cwd, env, timeoutMs } = data;
      let stdout = '';
      let stderr = '';

      if (commandType === 'shell') {
        // Handle shell script execution
        logToFile.info(`[Worker ${process.pid}] Spawning shell process: sh ${args.join(' ')}`);
        logToFile.debug(`[Worker ${process.pid}] Shell process options - cwd: ${cwd}, timeout: ${timeoutMs}ms`);

        currentProcess = spawn('sh', args, {
          cwd,
          stdio: ['pipe', 'pipe', 'pipe'],
          env,
          // shell: true
        });
      } else {
        // Handle Python/uv command execution  
        logToFile.info(`[Worker ${process.pid}] Spawning process: ${uvPath} ${uvCommand} ${args.join(' ')}`);
        logToFile.debug(`[Worker ${process.pid}] Process options - cwd: ${cwd}, timeout: ${timeoutMs}ms`);

        currentProcess = spawn(uvPath, [uvCommand, ...args], {
          cwd,
          stdio: ['pipe', 'pipe', 'pipe'],
          env
        });
      }

      const childPid = currentProcess.pid;
      logToFile.info(`[Worker ${process.pid}] Child process spawned with PID: ${childPid}`);

      // Set up timeout if specified
      if (timeoutMs > 0) {
        logToFile.debug(`[Worker ${process.pid}] Setting timeout for ${timeoutMs}ms for PID: ${childPid}`);
        currentTimer = setTimeout(() => {
          logToFile.warn(`[Worker ${process.pid}] Process PID: ${childPid} TIMED OUT after ${timeoutMs}ms - triggering cleanup`);
          cleanup();
          parentPort?.postMessage({
            type: 'error',
            data: {
              error: `Python process timed out after ${timeoutMs}ms`,
              exitCode: -1,
              stderr: 'Process timeout'
            }
          });
          resolve();
        }, timeoutMs);
      } else {
        logToFile.debug(`[Worker ${process.pid}] No timeout set for PID: ${childPid}`);
      }

      // Collect stdout
      currentProcess.stdout?.on('data', (chunk: Buffer) => {
        stdout += chunk.toString();
      });

      // Collect stderr
      currentProcess.stderr?.on('data', (chunk: Buffer) => {
        stderr += chunk.toString();
      });

      // Handle process completion
      currentProcess.on('close', (code: number | null) => {
        logToFile.info(`[Worker ${process.pid}] Child process PID: ${childPid} closed with code: ${code}`);
        
        if (currentTimer) {
          clearTimeout(currentTimer);
          currentTimer = null;
          logToFile.debug(`[Worker ${process.pid}] Cleared timeout timer for PID: ${childPid}`);
        }

        if (code === 0) {
          logToFile.info(`[Worker ${process.pid}] Process PID: ${childPid} completed successfully`);
          parentPort?.postMessage({
            type: 'success',
            data: { stdout: stdout.trim(), stderr: stderr.trim() }
          });
        } else {
          logToFile.error(`[Worker ${process.pid}] Process PID: ${childPid} failed with exit code: ${code}`);
          if (stderr.trim()) {
            logToFile.error(`[Worker ${process.pid}] Process PID: ${childPid} stderr: ${stderr.trim()}`);
          }
          parentPort?.postMessage({
            type: 'error',
            data: {
              error: `Python process exited with code ${code || 'unknown'}`,
              exitCode: code || -1,
              stderr: stderr.trim()
            }
          });
        }
        
        currentProcess = null;
        logToFile.debug(`[Worker ${process.pid}] Process PID: ${childPid} cleaned up, currentProcess set to null`);
        resolve();
      });

      // Handle process errors
      currentProcess.on('error', (error: Error) => {
        logToFile.error(`[Worker ${process.pid}] Process PID: ${childPid} error: ${error.message}`);
        
        if (currentTimer) {
          clearTimeout(currentTimer);
          currentTimer = null;
          logToFile.debug(`[Worker ${process.pid}] Cleared timeout timer due to error for PID: ${childPid}`);
        }
        
        parentPort?.postMessage({
          type: 'error',
          data: {
            error: `Failed to spawn Python process: ${error.message}`,
            exitCode: -1,
            stderr: error.message
          }
        });
        
        currentProcess = null;
        logToFile.debug(`[Worker ${process.pid}] Process PID: ${childPid} cleaned up after error, currentProcess set to null`);
        resolve();
      });
    });
  };

  // Listen for messages from main thread
  parentPort?.on('message', async (message) => {
    if (message.type === 'execute') {
      await executeCommand(message.data);
    } else if (message.type === 'cleanup') {
      cleanup();
      parentPort?.postMessage({ type: 'cleanup-complete' });
    } else if (message.type === 'shutdown') {
      cleanup();
      process.exit(0);
    }
  });

  // Signal that worker is ready
  parentPort?.postMessage({ type: 'ready' });
}

interface CommandOptions {
  args: string[];
  uvCommand?: string;   // default "run"
  timeoutMs?: number;
  cwd?: string;
}

interface WorkerTask {
  resolve: (value: { stdout: string; stderr: string }) => void;
  reject: (reason: any) => void;
  timer?: NodeJS.Timeout;
}

/**
 * Utility class for spawning and managing Python processes using worker threads
 */
export class PythonRunner {
  private readonly pythonPath: string;
  private readonly codetraversePath: string;
  private readonly timeout: number;
  private readonly workingDirectory: string;
  private workerPool: Worker[] = [];
  private readonly maxWorkers: number = 4;
  private availableWorkers: Worker[] = [];
  private taskQueue: Array<{ task: any; workerTask: WorkerTask }> = [];
  private memoryTracker: MemoryTracker;
  private memoryTrackingEnabled: boolean = false;
  private activeTasks: Map<Worker, WorkerTask> = new Map();

  constructor(config: BridgeConfig = {}) {
    this.pythonPath = config.pythonPath || 'python';
    this.codetraversePath = config.codetraversePath || 'codetraverse';
    this.timeout = config.timeout || 60000; // 60 seconds default
    this.workingDirectory = config.workingDirectory || process.cwd();
    this.memoryTracker = new MemoryTracker();
    
    logToFile.info(`[PythonRunner] Initializing with config - pythonPath: ${this.pythonPath}, codetraversePath: ${this.codetraversePath}, timeout: ${this.timeout}ms, maxWorkers: ${this.maxWorkers}`);
    logToFile.debug(`[PythonRunner] Working directory: ${this.workingDirectory}`);
    logToFile.debug(`[PythonRunner] Initial memory state: ${this.memoryTracker.getCurrentMemoryInfo()}`);
    
    this.initializeWorkerPool();
  }

  private initializeWorkerPool(): void {
    logToFile.info(`[PythonRunner] Initializing worker pool with ${this.maxWorkers} workers`);
    
    for (let i = 0; i < this.maxWorkers; i++) {
      this.createWorker();
    }
    
    logToFile.info(`[PythonRunner] Worker pool initialized successfully. Active workers: ${this.workerPool.length}, Available workers: ${this.availableWorkers.length}`);
  }

  private createWorker(): Worker {
    const worker = new Worker(__filename, {
      workerData: { isWorker: true }
    });
    
    const workerThreadId = worker.threadId;
    logToFile.info(`[PythonRunner] Creating new worker with thread ID: ${workerThreadId}`);

    worker.on('message', (response) => {
      this.handleWorkerMessage(worker, response);
    });

    worker.on('error', (error) => {
      logToFile.error(`[PythonRunner] Worker ${workerThreadId} error: ${error.message}`);
      this.handleWorkerError(worker, error);
    });

    worker.on('exit', (code) => {
      if (code !== 0) {
        logToFile.error(`[PythonRunner] Worker ${workerThreadId} stopped with exit code ${code}`);
      } else {
        logToFile.info(`[PythonRunner] Worker ${workerThreadId} exited cleanly`);
      }
      this.removeWorker(worker);
    });

    worker.unref();

    this.workerPool.push(worker);
    this.availableWorkers.push(worker);
    logToFile.debug(`[PythonRunner] Worker ${workerThreadId} added to pool. Total workers: ${this.workerPool.length}`);
    
    return worker;
  }

  private handleWorkerMessage(worker: Worker, response: any): void {
    const workerTask = this.activeTasks.get(worker);

    if (response.type === 'ready') {
      logToFile.debug(`[PythonRunner] Worker ${worker.threadId} is ready`);
      // This worker is now available, so we can process the queue
      this.availableWorkers.push(worker);
      this.processQueue();
      return;
    }

    if (!workerTask) {
      logToFile.warn(`[PythonRunner] Received message from worker ${worker.threadId} without an active task.`);
      return;
    }

    if (workerTask.timer) {
      clearTimeout(workerTask.timer);
    }

    this.activeTasks.delete(worker);

    if (response.type === 'success') {
      workerTask.resolve({
        stdout: response.data.stdout || '',
        stderr: response.data.stderr || ''
      });
    } else if (response.type === 'error') {
      workerTask.reject(new PythonProcessError(
        response.data.error || 'Unknown error',
        response.data.exitCode || -1,
        response.data.stderr || ''
      ));
    }

    this.availableWorkers.push(worker);
    this.processQueue();
  }

  private handleWorkerError(worker: Worker, error: Error): void {
    const workerTask = this.activeTasks.get(worker);
    if (workerTask) {
      workerTask.reject(error);
      this.activeTasks.delete(worker);
    }
    // Remove failed worker and create a new one
    this.removeWorker(worker);
    this.createWorker();
  }

  private removeWorker(worker: Worker): void {
    const poolIndex = this.workerPool.indexOf(worker);
    if (poolIndex > -1) {
      this.workerPool.splice(poolIndex, 1);
    }

    const availableIndex = this.availableWorkers.indexOf(worker);
    if (availableIndex > -1) {
      this.availableWorkers.splice(availableIndex, 1);
    }
  }

  private processQueue(): void {
    while (this.taskQueue.length > 0 && this.availableWorkers.length > 0) {
      const { task, workerTask } = this.taskQueue.shift()!;
      const worker = this.availableWorkers.shift()!;
      this.executeTaskInWorker(worker, task, workerTask);
    }
  }

  private executeTaskInWorker(worker: Worker, task: any, workerTask: WorkerTask): void {
    this.activeTasks.set(worker, workerTask);

    // Set up timeout
    if (task.timeoutMs > 0) {
      workerTask.timer = setTimeout(() => {
        workerTask.reject(new PythonProcessError(
          `Python process timed out after ${task.timeoutMs}ms`,
          -1,
          'Process timeout'
        ));
        this.activeTasks.delete(worker);
        worker.terminate();
        this.removeWorker(worker);
        this.createWorker();
      }, task.timeoutMs);
    }
    worker.postMessage({ type: 'execute', data: task });
  }

  public async cleanup(): Promise<void> {
    const beforeCleanup = this.memoryTrackingEnabled ? 
      this.memoryTracker.takeSnapshot('before_cleanup', this.workerPool.length, this.availableWorkers.length, this.taskQueue.length) : 
      null;

    logToFile.warn(`[PythonRunner] Starting cleanup of ${this.workerPool.length} workers`);
    logToFile.info(`[PythonRunner] Current state - Pool: ${this.workerPool.length}, Available: ${this.availableWorkers.length}, Queued: ${this.taskQueue.length}`);

    if (this.memoryTrackingEnabled) {
      logToFile.info(`[PythonRunner] Pre-cleanup memory state: ${this.memoryTracker.getCurrentMemoryInfo()}`);
    }

    // Terminate all workers
    const terminationPromises = this.workerPool.map(async (worker) => {
      const threadId = worker.threadId;
      logToFile.info(`[PythonRunner] Terminating worker ${threadId}`);
      try {
        await worker.terminate();
        logToFile.debug(`[PythonRunner] Worker ${threadId} terminated successfully`);
      } catch (error) {
        logToFile.error(`[PythonRunner] Error terminating worker ${threadId}: ${error}`);
      }
    });

    await Promise.all(terminationPromises);

    // Clear all pools
    this.workerPool = [];
    this.availableWorkers = [];
    this.taskQueue = [];

    // Stop memory tracking if enabled
    if (this.memoryTrackingEnabled) {
      const afterCleanup = this.memoryTracker.takeSnapshot('after_cleanup', 0, 0, 0);
      if (beforeCleanup) {
        this.memoryTracker.logMemoryDelta(beforeCleanup, afterCleanup, 'cleanup_operation');
      }
      this.memoryTracker.stopTracking();
      this.memoryTrackingEnabled = false;
    }

    logToFile.info(`[PythonRunner] Cleanup completed - all workers terminated and pools cleared`);
  }

  /**
   * Enable Node.js memory tracking with configurable interval
   */
  public enableMemoryTracking(intervalMs: number = 30000): void {
    if (!this.memoryTrackingEnabled) {
      this.memoryTrackingEnabled = true;
      this.memoryTracker.startTracking(intervalMs);
      logToFile.info(`[PythonRunner] Memory tracking enabled with ${intervalMs}ms intervals`);
    } else {
      logToFile.warn(`[PythonRunner] Memory tracking is already enabled`);
    }
  }

  /**
   * Disable Node.js memory tracking
   */
  public disableMemoryTracking(): void {
    if (this.memoryTrackingEnabled) {
      this.memoryTracker.stopTracking();
      this.memoryTrackingEnabled = false;
      logToFile.info(`[PythonRunner] Memory tracking disabled`);
    } else {
      logToFile.warn(`[PythonRunner] Memory tracking is already disabled`);
    }
  }

  /**
   * Get current memory usage information
   */
  public getCurrentMemoryInfo(): string {
    const info = this.memoryTracker.getCurrentMemoryInfo();
    logToFile.debug(`[PythonRunner] Current memory info requested: ${info}`);
    return info;
  }

  /**
   * Take a manual memory snapshot
   */
  public takeMemorySnapshot(context: string): void {
    this.memoryTracker.takeSnapshot(
      context,
      this.workerPool.length,
      this.availableWorkers.length,
      this.taskQueue.length
    );
    logToFile.debug(`[PythonRunner] Manual memory snapshot taken: ${context}`);
  }

  /**
   * Get all memory snapshots taken so far
   */
  public getMemorySnapshots(): MemorySnapshot[] {
    return this.memoryTracker.getSnapshots();
  }

  /**
   * Check if memory tracking is currently enabled
   */
  public isMemoryTrackingEnabled(): boolean {
    return this.memoryTrackingEnabled;
  }

  async createEnv() {
    logToFile.info(`Creating environment with Python path: ${this.pythonPath}, CodeTraverse path: ${this.codetraversePath}`)
    await this.executeShellCommand([path.join(this.codetraversePath, "scripts/setup.sh"), this.pythonPath, this.codetraversePath])
  }

  async installDeps() {
    const requirementsPath = path.join(this.codetraversePath, "codetraverse", "requirements.txt");
    if (fs.existsSync(requirementsPath)) {
      const envPath = path.join(process.env.HOME || "./", "npm_codetraverse");
      await this.executeCommand({ args: ["-r", requirementsPath], uvCommand: "add", cwd: envPath})
    }
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

    return this.executeCommand({ args });
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

    return this.executeCommand({ args });
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

    return this.executeCommand({ args });
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

    return this.executeCommand({ args });
  }

  async runBlackbox(
    fn: string,
    args: string[]
  ): Promise<{ stdout: string; stderr: string }> {
    const cmd = ["-m", "codetraverse.utils.blackbox", fn, ...args];
    return this.executeCommand({ args: cmd });
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
    return this.executeCommand({ args: cmd, timeoutMs: -1 });
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
    return this.executeCommand({ args });
  }

  /**
   * Extract components from a single file
   */
  async runComponentExtraction(
    filePath: string
  ): Promise<{ stdout: string; stderr: string }> {
    await this.validatePath(filePath);
    const args = [
      '-m', 'codetraverse.utils.AstDifferOrchestrator',
      '--extract-components',
      '--file', filePath
    ];
    return this.executeCommand({ args });
  }

  /**
   * Extract components from multiple files
   */
  async runMultipleComponentExtraction(
    filePaths: string[]
  ): Promise<{ stdout: string; stderr: string }> {
    for (const filePath of filePaths) {
      await this.validatePath(filePath);
    }
    const args = [
      '-m', 'codetraverse.utils.AstDifferOrchestrator',
      '--extract-components',
      '--files', ...filePaths
    ];
    return this.executeCommand({ args });
  }

  /**
   * Check if Python and codetraverse are available
   */
  async validateSetup(): Promise<void> {
    try {
      // Check Python
      await this.executeCommand({ args: ['--version'], timeoutMs: 5000 });

      // Check codetraverse module
      await this.executeCommand({ args: ['-m', "codetraverse.utils.blackbox", '--help'], timeoutMs: 10000 });
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

  /**
   * Execute a shell command using worker thread pool
   */
  private async executeShellCommand(
    args: string[],
    timeoutMs?: number,
    cwd?: string
  ): Promise<{ stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      const actualTimeout = timeoutMs || 5 * 60 * 1000; // 5 minutes default
      
      const task = {
        commandType: 'shell',
        args,
        cwd: cwd || this.workingDirectory,
        env: process.env,
        timeoutMs: actualTimeout
      };

      const workerTask: WorkerTask = { resolve, reject };

      // If workers are available, execute immediately
      if (this.availableWorkers.length > 0) {
        const worker = this.availableWorkers.shift()!;
        this.executeTaskInWorker(worker, task, workerTask);
      } else {
        // Queue the task
        this.taskQueue.push({ task, workerTask });
      }
    });
  }

  /**
   * Execute a Python command using worker thread pool with memory tracking
   */
  private async executeCommand({ args, uvCommand = "run", timeoutMs, cwd }: CommandOptions): Promise<{ stdout: string; stderr: string }> {
    const s = args.join(" ")
    logToFile.info(`Running executeCommand: ${uvCommand} ${s} in ${cwd}`);
    
    // Take memory snapshot before execution if tracking is enabled
    let beforeSnapshot: MemorySnapshot | null = null;
    if (this.memoryTrackingEnabled) {
      beforeSnapshot = this.memoryTracker.takeSnapshot(
        `before_command_${uvCommand}`,
        this.workerPool.length,
        this.availableWorkers.length,
        this.taskQueue.length
      );
    }

    return new Promise((resolve, reject) => {
      const actualTimeout = timeoutMs === -1 ? 0 : (timeoutMs || this.timeout);
      const uvPath = this.getUvPath();
      
      const task = {
        uvPath,
        uvCommand,
        args,
        cwd: cwd || this.codetraversePath,
        env: {
          ...process.env,
          VIRTUAL_ENV: path.join(process.env.HOME || "./", "npm_codetraverse", ".venv"),
        },
        timeoutMs: actualTimeout
      };

      const originalResolve = resolve;
      const originalReject = reject;

      // Wrap resolve/reject to include memory tracking
      const wrappedResolve = (value: { stdout: string; stderr: string }) => {
        if (this.memoryTrackingEnabled && beforeSnapshot) {
          const afterSnapshot = this.memoryTracker.takeSnapshot(
            `after_command_${uvCommand}`,
            this.workerPool.length,
            this.availableWorkers.length,
            this.taskQueue.length
          );
          this.memoryTracker.logMemoryDelta(beforeSnapshot, afterSnapshot, `command_${uvCommand}`);
        }
        originalResolve(value);
      };

      const wrappedReject = (reason: any) => {
        if (this.memoryTrackingEnabled && beforeSnapshot) {
          const afterSnapshot = this.memoryTracker.takeSnapshot(
            `after_command_${uvCommand}_error`,
            this.workerPool.length,
            this.availableWorkers.length,
            this.taskQueue.length
          );
          this.memoryTracker.logMemoryDelta(beforeSnapshot, afterSnapshot, `command_${uvCommand}_error`);
        }
        originalReject(reason);
      };

      const workerTask: WorkerTask = { resolve: wrappedResolve, reject: wrappedReject };

      // If workers are available, execute immediately
      if (this.availableWorkers.length > 0) {
        const worker = this.availableWorkers.shift()!;
        this.executeTaskInWorker(worker, task, workerTask);
      } else {
        // Queue the task
        this.taskQueue.push({ task, workerTask });
      }
    });
  }

  /**
   * Get the UV executable path with fallbacks
   */
  private getUvPath(): string {
    // Try common UV installation paths
    const potentialPaths = [
      path.join(process.env.HOME || "./", "npm_codetraverse", "tmp_env", "bin", "uv"),
      path.join(process.env.HOME || "./", ".cargo", "bin", "uv"),
      "uv", // System PATH
    ];

    for (const uvPath of potentialPaths) {
      try {
        // For absolute paths, check if file exists
        if (path.isAbsolute(uvPath)) {
          if (require('fs').existsSync(uvPath)) {
            return uvPath;
          }
        } else {
          // For relative paths (like "uv"), assume it's in PATH
          return uvPath;
        }
      } catch (error) {
        // Continue to next path
      }
    }

    // Fallback to the original path
    return path.join(process.env.HOME || "./", "npm_codetraverse", "tmp_env", "bin", "uv");
  }

  /**
   * Run codetraverse analysis with automatic memory management for VSCode plugin
   */
  async runMemoryOptimizedAnalysis(
    rootDir: string,
    language: Language,
    options: {
      outputBase?: string;
      graphDir?: string;
      maxMemoryMB?: number;
      enableMemoryTracking?: boolean;
    } = {}
  ): Promise<{ stdout: string; stderr: string; memoryReport?: any }> {
    const { outputBase, graphDir, enableMemoryTracking = false } = options;
    
    try {
      // Start memory tracking if requested
      if (enableMemoryTracking) {
        await this.startMemoryTracking();
      }

      const result = await this.runCreateFdepDataAndGraph(
        rootDir,
        outputBase || './vscode_output/fdep',
        graphDir || './vscode_output/graph',
        false // Always clear for fresh analysis
      );

      let memoryReport;
      if (enableMemoryTracking) {
        memoryReport = await this.getMemoryReport();
        await this.stopMemoryTracking();
      }

      // Trigger memory cleanup after analysis
      await this.cleanupMemory();

      return { ...result, memoryReport };
    } catch (error) {
      if (enableMemoryTracking) {
        await this.stopMemoryTracking();
      }
      await this.cleanupMemory();
      throw error;
    }
  }

  /**
   * Batch process multiple directories with memory management
   */
  async runBatchAnalysis(
    directories: Array<{ path: string; language: Language; outputDir?: string }>,
    options: {
      cleanupInterval?: number;
      maxConcurrent?: number;
    } = {}
  ): Promise<Array<{ path: string; result: any; error?: Error }>> {
    const { cleanupInterval = 3, maxConcurrent = 2 } = options;
    const results: Array<{ path: string; result: any; error?: Error }> = [];
    
    // Process directories in batches to prevent memory buildup
    for (let i = 0; i < directories.length; i += maxConcurrent) {
      const batch = directories.slice(i, i + maxConcurrent);
      
      const batchPromises = batch.map(async (dir) => {
        try {
          const options: any = {};
          if (dir.outputDir) {
            options.outputBase = `${dir.outputDir}/fdep`;
            options.graphDir = `${dir.outputDir}/graph`;
          }
          
          const result = await this.runMemoryOptimizedAnalysis(dir.path, dir.language, options);
          return { path: dir.path, result };
        } catch (error) {
          return { path: dir.path, result: null, error: error as Error };
        }
      });

      const batchResults = await Promise.all(batchPromises);
      results.push(...batchResults);

      // Cleanup after each batch if specified
      if ((i + maxConcurrent) % cleanupInterval === 0) {
        await this.cleanupMemory();
        // Brief pause to allow memory to be freed
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }

    // Final cleanup
    await this.cleanupMemory();
    return results;
  }

  /**
   * Start memory tracking in Python process
   */
  async startMemoryTracking(): Promise<void> {
    const script = `
from codetraverse.utils.memory_manager import memory_manager
memory_manager.start_tracking()
memory_manager.take_snapshot("start")
print("Memory tracking started")
    `.trim();

    await this.executeCommand({ args: ['-c', script], timeoutMs: 5000 });
  }

  /**
   * Stop memory tracking and get final report
   */
  async stopMemoryTracking(): Promise<void> {
    const script = `
from codetraverse.utils.memory_manager import memory_manager
memory_manager.stop_tracking()
memory_manager.clear_all_snapshots()
print("Memory tracking stopped")
    `.trim();

    await this.executeCommand({ args: ['-c', script], timeoutMs: 5000 });
  }

  /**
   * Get memory usage report from Python process
   */
  async getMemoryReport(): Promise<any> {
    try {
      const script = `
import json
from codetraverse.utils.memory_manager import memory_manager
report = memory_manager.get_memory_usage()
print(json.dumps(report))
      `.trim();

      const result = await this.executeCommand({ args: ['-c', script], timeoutMs: 10000 });
      return JSON.parse(result.stdout);
    } catch (error) {
      logToFile.warn(`Failed to get memory report: ${error}`);
      return { error: 'Memory report unavailable' };
    }
  }

  /**
   * Trigger memory cleanup in the Python process
   */
  async cleanupMemory(): Promise<void> {
    try {
      // Execute Python code to trigger memory cleanup
      const cleanupScript = `
import gc
try:
    from codetraverse.registry.extractor_registry import clear_extractor_cache
    clear_extractor_cache()
except ImportError:
    pass
gc.collect()
print("Memory cleanup completed")
      `.trim();

      await this.executeCommand({ 
        args: ['-c', cleanupScript], 
        timeoutMs: 10000 
      });
    } catch (error) {
      // Memory cleanup is non-critical, log but don't throw
      logToFile.warn(`Memory cleanup failed: ${error}`);
    }
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
