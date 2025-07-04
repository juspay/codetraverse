/**
 * @fileoverview CodeTraverse Bridge - Node.js/TypeScript API for CodeTraverse Python tool
 * 
 * This package provides a bridge between Node.js/TypeScript applications and the
 * CodeTraverse Python static analysis tool. It allows you to analyze code repositories
 * and extract dependency graphs using a clean, typed API.
 * 
 * @example
 * ```typescript
 * import { CodeTraverseBridge } from '@codetraverse/bridge';
 * 
 * const bridge = new CodeTraverseBridge();
 * 
 * // Analyze a TypeScript project
 * const components = await bridge.analyzeWorkspaceComponents('/path/to/project', {
 *   language: 'typescript'
 * });
 * 
 * // Find path between components
 * const path = await bridge.findPath(
 *   'graph/repo_function_calls.graphml',
 *   'src/utils::helper',
 *   'src/main::main'
 * );
 * ```
 */

// Export main classes
export { CodeTraverseBridge } from './bridge';
export { PythonRunner } from './python-runner';

// Export all types
export * from './types';

// Export convenience function for quick setup
export function createBridge(config?: import('./types').BridgeConfig): import('./bridge').CodeTraverseBridge {
  return new (require('./bridge').CodeTraverseBridge)(config);
}

// Export version info
export const version = '0.1.0';