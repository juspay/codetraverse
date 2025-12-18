use std::collections::HashMap;
use std::env;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use bytes::{Buf, BytesMut};
use futures::{SinkExt, StreamExt};
use lsp_types::{
    CallHierarchyIncomingCall, CallHierarchyIncomingCallsParams, CallHierarchyItem,
    CallHierarchyOutgoingCall, CallHierarchyOutgoingCallsParams, ClientCapabilities,
    DidOpenTextDocumentParams, DocumentSymbol, DocumentSymbolClientCapabilities,
    DocumentSymbolParams, InitializeParams, InitializedParams, Position,
    Range, SymbolKind, TextDocumentClientCapabilities, TextDocumentIdentifier, TextDocumentItem,
    Url, WorkspaceFolder, ReferenceParams, ReferenceContext, Location
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{ChildStdin, ChildStdout, Command};
use tokio::time::sleep;
use tokio_util::codec::{Decoder, Encoder, FramedRead, FramedWrite};

// ==========================================
// 1. Data Structures
// ==========================================

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub enum NodeType {
    Function,
    Struct,
    Enum,
    Module,
    Constant,
    Variable,
    Interface, 
    Impl,
    TypeAlias, 
    Field,     
    Unknown,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GraphNode {
    pub id: String,         
    pub label: String,      
    pub relative_path: String,
    pub node_type: NodeType,
    pub range: Range,
    pub code: String,       
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct FdepGraph {
    pub nodes: HashMap<String, GraphNode>,
    pub edges: Vec<(String, String)>, 
}

impl FdepGraph {
    pub fn new() -> Self {
        FdepGraph {
            nodes: HashMap::new(),
            edges: Vec::new(),
        }
    }
}

// ==========================================
// 2. LSP Transport Codec
// ==========================================

struct LspCodec;

impl Encoder<RpcMessage> for LspCodec {
    type Error = anyhow::Error;

    fn encode(&mut self, item: RpcMessage, dst: &mut BytesMut) -> Result<(), Self::Error> {
        let json = serde_json::to_string(&item)?;
        let len = json.len();
        let header = format!("Content-Length: {}\r\n\r\n", len);
        dst.reserve(header.len() + len);
        dst.extend_from_slice(header.as_bytes());
        dst.extend_from_slice(json.as_bytes());
        Ok(())
    }
}

impl Decoder for LspCodec {
    type Item = RpcMessage;
    type Error = anyhow::Error;

    fn decode(&mut self, src: &mut BytesMut) -> Result<Option<Self::Item>, Self::Error> {
        if let Some(i) = src.windows(4).position(|b| b == b"\r\n\r\n") {
            let headers_bytes = &src[..i];
            let headers_str = std::str::from_utf8(headers_bytes)?;
            
            let content_len = headers_str
                .lines()
                .find_map(|line| {
                    if line.to_ascii_lowercase().starts_with("content-length:") {
                        line.split(':').nth(1).map(|v| v.trim().parse::<usize>().ok())
                    } else {
                        None
                    }
                })
                .flatten()
                .ok_or_else(|| anyhow!("Invalid Content-Length"))?;

            let total_len = i + 4 + content_len;
            if src.len() < total_len {
                return Ok(None); // Wait for more data
            }

            src.advance(i + 4);
            let body_bytes = src.split_to(content_len);
            let msg: RpcMessage = serde_json::from_slice(&body_bytes)?;
            return Ok(Some(msg));
        }
        Ok(None)
    }
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(untagged)]
enum RpcMessage {
    Response(RpcResponse),
    Request(RpcRequest),
    Notification(RpcNotification),
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct RpcRequest {
    jsonrpc: String,
    id: usize,
    method: String,
    params: Value,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct RpcResponse {
    jsonrpc: String,
    id: usize,
    result: Option<Value>,
    error: Option<Value>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct RpcNotification {
    jsonrpc: String,
    method: String,
    params: Option<Value>,
}

// ==========================================
// 3. LSP Client Wrapper
// ==========================================

struct LspClient {
    stdin: FramedWrite<ChildStdin, LspCodec>,
    stdout: FramedRead<BufReader<ChildStdout>, LspCodec>,
    req_id: AtomicUsize,
}

impl LspClient {
    async fn send_request<T: Serialize>(&mut self, method: &str, params: T) -> Result<Value> {
        let id = self.req_id.fetch_add(1, Ordering::SeqCst);
        let req = RpcMessage::Request(RpcRequest {
            jsonrpc: "2.0".into(),
            id,
            method: method.into(),
            params: serde_json::to_value(params)?,
        });

        self.stdin.send(req).await?;

        loop {
            match self.stdout.next().await {
                Some(Ok(RpcMessage::Response(resp))) if resp.id == id => {
                    if let Some(err) = resp.error {
                        return Err(anyhow!("LSP Error: {}", err));
                    }
                    return Ok(resp.result.unwrap_or(Value::Null));
                }
                Some(Ok(RpcMessage::Notification(_))) => {} 
                Some(Ok(_)) => {} 
                Some(Err(e)) => return Err(e),
                None => return Err(anyhow!("Server closed connection")),
            }
        }
    }

    async fn send_notification<T: Serialize>(&mut self, method: &str, params: T) -> Result<()> {
        let notif = RpcMessage::Notification(RpcNotification {
            jsonrpc: "2.0".into(),
            method: method.into(),
            params: Some(serde_json::to_value(params)?),
        });
        self.stdin.send(notif).await?;
        Ok(())
    }
}

// ==========================================
// 4. Main Application
// ==========================================

#[tokio::main]
async fn main() -> Result<()> {
    env_logger::init();
    
    // --- ARGUMENT PARSING ---
    let args: Vec<String> = env::args().collect();
    let raw_project_path = args.get(1).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    let raw_output_path = args.get(2).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("fdep-output.json"));

    // 1. Resolve Project Root
    let project_root = find_cargo_toml(&raw_project_path)
        .ok_or_else(|| anyhow!("Could not find Cargo.toml in {:?} or parents", raw_project_path))?
        .canonicalize()?; 
    
    eprintln!("📍 Resolved Project Root: {:?}", project_root);

    let output_path = if raw_output_path.is_dir() {
        raw_output_path.join("fdep-output.json")
    } else {
        if let Some(parent) = raw_output_path.parent() {
            if !parent.exists() {
                 tokio::fs::create_dir_all(parent).await?;
            }
        }
        raw_output_path
    };

    let root_uri = Url::from_directory_path(&project_root).map_err(|_| anyhow!("Invalid root URI"))?;

    // 2. Start Rust Analyzer
    eprintln!("🚀 Spawning rust-analyzer...");
    let mut process = Command::new("rust-analyzer")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("Could not start rust-analyzer")?;

    let stderr = process.stderr.take().unwrap();
    tokio::spawn(async move {
        let reader = BufReader::new(stderr);
        let mut lines = reader.lines();
        while let Ok(Some(_line)) = lines.next_line().await { }
    });

    let stdin = process.stdin.take().unwrap();
    let stdout = process.stdout.take().unwrap();

    let mut client = LspClient {
        stdin: FramedWrite::new(stdin, LspCodec),
        stdout: FramedRead::new(BufReader::new(stdout), LspCodec),
        req_id: AtomicUsize::new(1),
    };

    // 3. Initialize LSP
    eprintln!("🤝 Initializing LSP...");

    let supported_symbol_kinds = vec![
        SymbolKind::FILE, SymbolKind::MODULE, SymbolKind::NAMESPACE,
        SymbolKind::PACKAGE, SymbolKind::CLASS, SymbolKind::METHOD,
        SymbolKind::PROPERTY, SymbolKind::FIELD, SymbolKind::CONSTRUCTOR,
        SymbolKind::ENUM, SymbolKind::INTERFACE, SymbolKind::FUNCTION,
        SymbolKind::VARIABLE, SymbolKind::CONSTANT, SymbolKind::STRING,
        SymbolKind::NUMBER, SymbolKind::BOOLEAN, SymbolKind::ARRAY,
        SymbolKind::OBJECT, SymbolKind::KEY, SymbolKind::NULL,
        SymbolKind::ENUM_MEMBER, SymbolKind::STRUCT, SymbolKind::EVENT,
        SymbolKind::OPERATOR, SymbolKind::TYPE_PARAMETER,
    ];

    let init_params = InitializeParams {
        process_id: Some(std::process::id()),
        root_uri: Some(root_uri.clone()),
        capabilities: ClientCapabilities {
            text_document: Some(TextDocumentClientCapabilities {
                document_symbol: Some(DocumentSymbolClientCapabilities {
                    hierarchical_document_symbol_support: Some(true),
                    symbol_kind: Some(lsp_types::SymbolKindCapability {
                        value_set: Some(supported_symbol_kinds)
                    }),
                    ..Default::default()
                }),
                call_hierarchy: Some(lsp_types::CallHierarchyClientCapabilities {
                    dynamic_registration: Some(false),
                }),
                references: Some(lsp_types::DynamicRegistrationClientCapabilities {
                    dynamic_registration: Some(false),
                }),
                ..Default::default()
            }),
            ..Default::default()
        },
        workspace_folders: Some(vec![WorkspaceFolder {
            uri: root_uri.clone(),
            name: "root".into(),
        }]),
        ..Default::default()
    };

    let _ = client.send_request("initialize", init_params).await?;
    client.send_notification("initialized", InitializedParams {}).await?;

    // 4. Gather Files
    eprintln!("📂 Scanning for .rs files...");
    let mut files_to_scan = Vec::new();
    scan_files_recursive(&project_root, &mut files_to_scan);
    
    files_to_scan.retain(|p| {
        !p.components().any(|c| c.as_os_str() == "target" || c.as_os_str().to_string_lossy().starts_with('.'))
    });

    eprintln!("   Found {} rust files to analyze.", files_to_scan.len());
    let mut file_map: HashMap<Url, String> = HashMap::new();

    for path in &files_to_scan {
        let content = tokio::fs::read_to_string(path).await?;
        let uri = Url::from_file_path(path).map_err(|_| anyhow!("Invalid file path"))?;
        file_map.insert(uri.clone(), content.clone());

        let params = DidOpenTextDocumentParams {
            text_document: TextDocumentItem {
                uri,
                language_id: "rust".into(),
                version: 1,
                text: content,
            },
        };
        client.send_notification("textDocument/didOpen", params).await?;
    }

    eprintln!("⏳ Waiting for RA to warm up...");
    sleep(Duration::from_secs(2)).await;

    //5. Build Nodes (Robust Version)
    let mut graph = FdepGraph::new();
    let mut function_candidates = Vec::new(); 
    let mut type_candidates = Vec::new();     

    eprintln!("🏗️  Building Symbol Graph...");

    for (idx, path) in files_to_scan.iter().enumerate() {
        let uri = Url::from_file_path(path).unwrap();
        let relative_name = path.strip_prefix(&project_root).unwrap_or(path).to_string_lossy();
        
        eprint!("\r   [{}/{}] Analyzing: {}", idx + 1, files_to_scan.len(), relative_name);
        
        // Increase retries to handle Macro Expansion lag
        let mut attempts = 0;
        let max_attempts = 10; 
        let current_file_content = file_map.get(&uri).expect("File content missing");

        loop {
            attempts += 1;
            let params = DocumentSymbolParams {
                text_document: TextDocumentIdentifier { uri: uri.clone() },
                work_done_progress_params: Default::default(),
                partial_result_params: Default::default(),
            };

            let response = client.send_request("textDocument/documentSymbol", params).await;

            match response {
                Ok(val) => {
                    // Case A: Result is Null (Server not ready)
                    if val.is_null() {
                        if attempts >= max_attempts {
                            eprintln!("\n⚠️  Timeout waiting for symbols in {}", relative_name);
                            break;
                        }
                        sleep(Duration::from_millis(300 * attempts as u64)).await; // Exponential backoff
                        continue;
                    }

                    // Case B: Try to parse as Hierarchical Document Symbols
                    let symbols_res: Result<Vec<DocumentSymbol>, _> = serde_json::from_value(val.clone());

                    match symbols_res {
                        Ok(syms) => {
                            // Case B.1: Valid list, but empty. Might be indexing, might be empty file.
                            if syms.is_empty() {
                                if attempts < 5 {
                                    // Give it a bit more time if it looks empty (macro expansion takes time)
                                    sleep(Duration::from_millis(300)).await;
                                    continue;
                                }
                            }

                            // SUCCESS: Process the symbols
                            for sym in syms {
                                process_symbol(
                                    &mut graph, 
                                    &mut function_candidates,
                                    &mut type_candidates,
                                    sym, 
                                    path, 
                                    &uri, 
                                    &project_root,
                                    current_file_content 
                                );
                            }
                            break; // Done with this file
                        }
                        Err(e) => {
                            // Case B.2: JSON mismatch. This is likely the "Silent Failure" you were having.
                            // Sometimes RA returns "SymbolInformation" (flat) instead of "DocumentSymbol" (tree)
                            // if it's confused or configured differently.
                            eprintln!("\n❌ JSON Parse Error in {}: {}", relative_name, e);
                            
                            // Debugging tip: Uncomment next line to see what RA actually sent
                            // eprintln!("   Raw JSON: {}", val); 
                            break;
                        }
                    }
                }
                Err(e) => {
                    eprintln!("\n❌ LSP Request Error in {}: {}", relative_name, e);
                    break;
                }
            }
        }
    }

    let mut edges_count = 0;

    // 6. PHASE A: Calculate Function Call Edges
    eprintln!("\n🔗 Phase A: Calculating Call Graph...");
    for (i, (node_id, uri, pos)) in function_candidates.iter().enumerate() {
        if i % 10 == 0 { eprint!("\r   {}/{}...", i, function_candidates.len()); }

        let prep_params = lsp_types::CallHierarchyPrepareParams {
            text_document_position_params: lsp_types::TextDocumentPositionParams {
                text_document: TextDocumentIdentifier { uri: uri.clone() },
                position: *pos,
            },
            work_done_progress_params: Default::default(),
        };

        if let Ok(val) = client.send_request("textDocument/prepareCallHierarchy", prep_params).await {
             let items: Option<Vec<CallHierarchyItem>> = serde_json::from_value(val).unwrap_or(None);
             if let Some(items) = items {
                 if let Some(root_item) = items.first() {
                     let out_params = CallHierarchyOutgoingCallsParams {
                         item: root_item.clone(),
                         work_done_progress_params: Default::default(),
                         partial_result_params: Default::default(),
                     };
                     if let Ok(out_val) = client.send_request("callHierarchy/outgoingCalls", out_params).await {
                         let calls: Option<Vec<CallHierarchyOutgoingCall>> = serde_json::from_value(out_val).unwrap_or(None);
                         if let Some(calls) = calls {
                             for call in calls {
                                 let callee_id = generate_relative_id(&call.to.uri, &call.to.name, &project_root);
                                 if graph.nodes.contains_key(&callee_id) {
                                     graph.edges.push((node_id.clone(), callee_id));
                                     edges_count += 1;
                                 }
                             }
                         }
                     }
                 }
             }
        }
    }

    // 7. PHASE B: Calculate Type Usage Edges
    eprintln!("\n🔗 Phase B: Calculating Type Dependency Graph...");
    eprintln!("   Candidates to analyze for type usage: {}", type_candidates.len());

    // Spatial Map
    let mut function_spatial_map: HashMap<String, Vec<(&Range, &String)>> = HashMap::new();
    for node in graph.nodes.values() {
        if matches!(node.node_type, NodeType::Function) {
            function_spatial_map.entry(node.relative_path.clone())
                .or_default()
                .push((&node.range, &node.id));
        }
    }

    // Type References
    for (i, (type_node_id, uri, pos)) in type_candidates.iter().enumerate() {
        if i % 5 == 0 { eprint!("\r   {}/{}...", i, type_candidates.len()); }

        let params = ReferenceParams {
            text_document_position: lsp_types::TextDocumentPositionParams {
                text_document: TextDocumentIdentifier { uri: uri.clone() },
                position: *pos,
            },
            work_done_progress_params: Default::default(),
            partial_result_params: Default::default(),
            context: ReferenceContext { include_declaration: false }, 
        };

        if let Ok(res) = client.send_request("textDocument/references", params).await {
            let locations: Option<Vec<Location>> = serde_json::from_value(res).unwrap_or(None);
            
            if let Some(locs) = locations {
                for loc in locs {
                    if let Ok(path) = loc.uri.to_file_path() {
                        if let Ok(relative_path) = path.strip_prefix(&project_root) {
                            let rel_str = relative_path.to_string_lossy().to_string();
                            
                            if let Some(funcs_in_file) = function_spatial_map.get(&rel_str) {
                                for (range, func_id) in funcs_in_file {
                                    if is_inside(loc.range.start, range) {
                                        graph.edges.push((func_id.to_string(), type_node_id.clone()));
                                        edges_count += 1;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    eprintln!("\n💾 Saving {} nodes and {} edges to {:?}", graph.nodes.len(), edges_count, output_path);
    let json = serde_json::to_string_pretty(&graph)?;
    tokio::fs::write(&output_path, json).await?;
    eprintln!("✅ Done.");

    Ok(())
}

// ==========================================
// 5. Helpers
// ==========================================

fn find_cargo_toml(start_path: &Path) -> Option<PathBuf> {
    let mut current = start_path.to_path_buf();
    if current.is_file() { current.pop(); }
    loop {
        let candidate = current.join("Cargo.toml");
        if candidate.exists() { return Some(current); }
        if !current.pop() { return None; }
    }
}

fn scan_files_recursive(dir: &Path, list: &mut Vec<PathBuf>) {
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() { scan_files_recursive(&path, list); } 
            else if path.extension().map_or(false, |e| e == "rs") { list.push(path); }
        }
    }
}

fn process_symbol(
    graph: &mut FdepGraph, 
    func_candidates: &mut Vec<(String, Url, Position)>,
    type_candidates: &mut Vec<(String, Url, Position)>,
    sym: DocumentSymbol, 
    file_path: &PathBuf, 
    uri: &Url,
    root: &PathBuf,
    content: &str
) {
    let id = generate_relative_id(uri, &sym.name, root);
    
    // Enable this temporarily to debug exactly what RA sees your types as
    // eprintln!("[DEBUG] Symbol: {:<20} Kind: {:<15} ({:?})", sym.name, format!("{:?}", sym.kind), sym.kind);

    let kind = match sym.kind {
        // Functions
        SymbolKind::FUNCTION | SymbolKind::METHOD | SymbolKind::CONSTRUCTOR => NodeType::Function,
        
        // Structures & Data
        SymbolKind::STRUCT => NodeType::Struct,
        SymbolKind::ENUM => NodeType::Enum,
        SymbolKind::INTERFACE => NodeType::Interface, // Traits often appear here
        
        // Type Aliases (e.g., type AppGraph = ...)
        // Rust Analyzer notoriously maps `type` aliases to TypeParameter or Interface
        SymbolKind::TYPE_PARAMETER => NodeType::TypeAlias, 
        
        // Fallbacks for Structs/Types if RA downgrades them
        SymbolKind::CLASS => NodeType::Struct, 
        SymbolKind::OBJECT => NodeType::Struct, 

        // Variables/Constants
        SymbolKind::CONSTANT => NodeType::Constant,
        SymbolKind::VARIABLE => NodeType::Variable,
        SymbolKind::FIELD => NodeType::Field, 
        SymbolKind::ENUM_MEMBER => NodeType::Field, 

        // Modules
        SymbolKind::MODULE | SymbolKind::NAMESPACE => NodeType::Module,
        
        // Catch-all
        _ => NodeType::Unknown,
    };

    let relative = file_path.strip_prefix(root).unwrap_or(file_path).to_string_lossy().to_string();
    let extracted_code = extract_code(content, sym.range);

    graph.nodes.insert(id.clone(), GraphNode {
        id: id.clone(),
        label: sym.name.clone(),
        relative_path: relative, 
        node_type: kind.clone(),
        range: sym.selection_range,
        code: extracted_code, 
    });

    match kind {
        NodeType::Function => {
            func_candidates.push((id, uri.clone(), sym.selection_range.start));
        },
        NodeType::Module => {
            // Keep recursing, but don't add to candidates
        },
        // We want to find references for Structs, Enums, TypeAliases, Fields, and Constants
        _ => {
            // Only search for references if it's not "Unknown" to save time, 
            // unless you specifically want to track unknown symbols too.
            if kind != NodeType::Unknown {
                type_candidates.push((id, uri.clone(), sym.selection_range.start));
            }
        }
    }

    if let Some(children) = sym.children {
        for child in children {
            process_symbol(graph, func_candidates, type_candidates, child, file_path, uri, root, content);
        }
    }
}

fn extract_code(content: &str, range: Range) -> String {
    let start_line = range.start.line as usize;
    let end_line = range.end.line as usize;
    content.lines().skip(start_line).take(end_line - start_line + 1).collect::<Vec<&str>>().join("\n")
}

fn generate_relative_id(uri: &Url, name: &str, root: &Path) -> String {
    if let Ok(path) = uri.to_file_path() {
        if let Ok(relative) = path.strip_prefix(root) {
             return format!("{}::{}", relative.to_string_lossy(), name);
        }
    }
    format!("EXTERNAL::{}", name)
}

fn is_inside(pos: Position, range: &Range) -> bool {
    if pos.line < range.start.line || pos.line > range.end.line { return false; }
    if pos.line == range.start.line && pos.character < range.start.character { return false; }
    if pos.line == range.end.line && pos.character > range.end.character { return false; }
    true
}