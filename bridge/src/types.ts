/**
 * Supported programming languages for analysis
 */
export type Language = 'haskell' | 'python' | 'rescript' | 'typescript' | 'rust' | 'golang';

/**
 * Component kinds that can be extracted from source code
 */
export type ComponentKind = 
  | 'function' 
  | 'class' 
  | 'method' 
  | 'field' 
  | 'variable' 
  | 'type_alias' 
  | 'interface' 
  | 'enum' 
  | 'namespace'
  | 'import';

/**
 * Function call information extracted from code
 */
export interface FunctionCall {
  kind: 'function_call';
  name: string;
  resolved_callee: string;
  full_component_path: string;
}

/**
 * Parameter information for functions and methods
 */
export interface Parameter {
  name: string | null;
  type: string | null;
  default: string | null;
}

/**
 * Location information for components
 */
export interface ComponentLocation {
  start_line: number;
  end_line: number;
  module: string;
}

/**
 * Base component interface - common fields for all component types
 */
export interface BaseComponent {
  kind: ComponentKind;
  name: string;
  module: string;
  start_line: number;
  end_line: number;
  full_component_path: string;
  jsdoc?: string | null;
}

/**
 * Function component
 */
export interface FunctionComponent extends BaseComponent {
  kind: 'function';
  parameters: Parameter[];
  type_signature: string | null;
  function_calls: FunctionCall[];
}

/**
 * Class component
 */
export interface ClassComponent extends BaseComponent {
  kind: 'class';
  function_calls: FunctionCall[];
  bases?: string[] | null;
  implements?: string[] | null;
}

/**
 * Method component (class method)
 */
export interface MethodComponent extends BaseComponent {
  kind: 'method';
  class: string;
  parameters: Parameter[];
  type_signature: string | null;
  function_calls?: FunctionCall[];
}

/**
 * Field component (class field)
 */
export interface FieldComponent extends BaseComponent {
  kind: 'field';
  class: string;
  type_signature: string | null;
}

/**
 * Variable component
 */
export interface VariableComponent extends BaseComponent {
  kind: 'variable';
  value: string;
  type_signature: string | null;
}

/**
 * Type alias component
 */
export interface TypeAliasComponent extends BaseComponent {
  kind: 'type_alias';
  function_calls: FunctionCall[];
}

/**
 * Interface component
 */
export interface InterfaceComponent extends BaseComponent {
  kind: 'interface';
  extends?: string[] | null;
}

/**
 * Enum component
 */
export interface EnumComponent extends BaseComponent {
  kind: 'enum';
}

/**
 * Namespace component
 */
export interface NamespaceComponent extends BaseComponent {
  kind: 'namespace';
  exports?: Array<{ name: string }> | null;
}

/**
 * Import component
 */
export interface ImportComponent extends BaseComponent {
  kind: 'import';
  statement: string;
}

/**
 * Union type of all component types
 */
export type Component = 
  | FunctionComponent 
  | ClassComponent 
  | MethodComponent 
  | FieldComponent 
  | VariableComponent 
  | TypeAliasComponent 
  | InterfaceComponent 
  | EnumComponent 
  | NamespaceComponent
  | ImportComponent;

/**
 * Graph node representation
 */
export interface GraphNode {
  id: string;
  category: string;
  signature?: string | null;
  type_parameters?: unknown;
  type_parameters_structured?: unknown;
  utility_type?: unknown;
  parameters?: Parameter[] | null;
  decorators?: unknown;
  location: ComponentLocation;
  value?: string | null;
  bases?: string[] | null;
  implements?: string[] | null;
  extends?: string[] | null;
  members?: unknown;
  static?: boolean | null;
  abstract?: boolean | null;
  readonly?: boolean | null;
  override?: boolean | null;
  getter?: boolean | null;
  setter?: boolean | null;
  type_param_constraints?: unknown;
  index_signatures?: unknown;
}

/**
 * Graph edge representation
 */
export interface GraphEdge {
  from: string;
  to: string;
  relation: string;
}

/**
 * Graph data structure containing nodes and edges
 */
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/**
 * Path finding result between two components
 */
export interface PathResult {
  found: boolean;
  path?: string[];
  message: string;
}

/**
 * Neighbor discovery result for a component
 */
export interface NeighborResult {
  incoming: Array<{
    from: string;
    relation: string;
  }>;
  outgoing: Array<{
    to: string;
    relation: string;
  }>;
}

/**
 * Bridge configuration options
 */
export interface BridgeConfig {
  /**
   * Path to Python executable (default: 'python')
   */
  pythonPath?: string;
  
  /**
   * Path to codetraverse module (default: 'codetraverse')
   */
  codetraversePath?: string;
  
  /**
   * Timeout for Python processes in milliseconds (default: 60000)
   */
  timeout?: number;
  
  /**
   * Working directory for analysis (default: process.cwd())
   */
  workingDirectory?: string;
}

/**
 * Analysis options for file or workspace analysis
 */
export interface AnalysisOptions {
  /**
   * Programming language to analyze
   */
  language: Language;
  
  /**
   * Output directory for component files (default: 'fdep')
   */
  outputBase?: string;
  
  /**
   * Output directory for graph files (default: 'graph')
   */
  graphDir?: string;
  
  /**
   * Force reanalysis even if output exists
   */
  force?: boolean;
}

/**
 * Error types that can occur during bridge operations
 */
export class CodeTraverseError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = 'CodeTraverseError';
  }
}

export class PythonProcessError extends CodeTraverseError {
  constructor(
    message: string,
    public readonly exitCode: number,
    public readonly stderr: string
  ) {
    super(message, 'PYTHON_PROCESS_ERROR', { exitCode, stderr });
    this.name = 'PythonProcessError';
  }
}

export class InvalidLanguageError extends CodeTraverseError {
  constructor(language: string) {
    super(`Unsupported language: ${language}`, 'INVALID_LANGUAGE', { language });
    this.name = 'InvalidLanguageError';
  }
}

export class FileNotFoundError extends CodeTraverseError {
  constructor(filePath: string) {
    super(`File not found: ${filePath}`, 'FILE_NOT_FOUND', { filePath });
    this.name = 'FileNotFoundError';
  }
}