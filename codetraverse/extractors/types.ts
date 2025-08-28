export interface Component {
  kind: string;
  name: string;
  startLine: number;
  endLine: number;
  code: string;
  filePath?: string;
  module?: string;
  typeSignature?: string | null;
  functionCalls?: FunctionCall[];
  typeDependencies?: string[];
  [key: string]: any;
}

export interface FunctionCall {
  name: string;
  type: string;
  modules?: string[];
  base?: string;
  context: string;
  localFunction?: boolean;
  [key: string]: any;
}

export interface WhereDefinition {
  kind: string;
  name: string;
  code: string;
  functionCalls?: FunctionCall[];
}

export interface Import {
  kind: "import";
  name: string;
  module: string;
  alias: string | null;
  importList: string[];
  isQualified: boolean;
  isHiding: boolean;
  startLine: number;
  endLine: number;
  code: string;
}

export interface DataType {
  kind: "data_type";
  name: string;
  startLine: number;
  endLine: number;
  code: string;
  constructors: any[];
  deriving?: any;
  module?: string;
  functionCalls?: FunctionCall[];
}

export interface ClassComponent {
  kind: "class";
  name: string;
  startLine: number;
  endLine: number;
  code: string;
  typeParameters: string[];
  constraints: string[];
  declarations: any[];
  typeFamilies: any[];
  methodSignatures: any[];
  defaultMethods: any[];
  module?: string;
}

export interface Instance {
  kind: "instance";
  name: string;
  startLine: number;
  endLine: number;
  code: string;
  typePatterns: any[];
  instanceMethods: any[];
  typeInstances: any[];
  module?: string;
  functionCalls?: FunctionCall[];
}

export type TopLevelComponent =
  | Component
  | Import
  | DataType
  | ClassComponent
  | Instance;

export interface Span {
    startLine: number;
    endLine: number;
    startByte: number;
    endByte: number;
}

export interface Parameter {
    name: string;
    type: string | null;
    filePath: string;
}

export interface Field {
    name: string;
    type: string;
    visibility: string;
    filePath: string;
}

export interface Variant {
    name: string;
    fields: { name: string; type: string; filePath: string }[];
}

export interface Call {
    name?: string;
    resolvedName?: string;
    receiver?: string;
    resolvedReceiver?: string;
    method?: string;
    fullPath?: string;
    filePath: string;
    span: Span;
}

export interface Literal {
    type: string;
    value: string;
    filePath: string;
    span: Span;
}

export interface Variable {
    name: string;
    type: string | null;
    value: string | null;
    filePath: string;
    span: Span;
}

export interface TypeUsed {
    type: string;
    resolvedType: string;
}
