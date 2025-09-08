export { createFdepData, LANGUAGES_SUPPORTED } from './main';
export { loadGraph } from './path';
export type { Component } from './types/types';
export { getAllModules, getModuleInfo, getFunctionInfo, getFunctionChildren, getFunctionParent, getSubgraph, getCommonParents, getCommonChildren, getImportantNodes, getNeighbors, findPath } from './utils/blackbox';
export { runAstDiffFromConfig, extractComponentsFromFile } from './utils/AstDifferOrchestrator';