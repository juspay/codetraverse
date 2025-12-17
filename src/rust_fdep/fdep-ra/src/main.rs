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
    Url, WorkspaceFolder,
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

#[derive(Debug, Serialize, Deserialize, Clone)]
pub enum NodeType {
    Function,
    Struct,
    Enum,
    Module,
    Constant,
    Variable,
    Interface, 
    Impl,
    Unknown,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GraphNode {
    pub id: String,         // Now: relative/path/to/file.rs::function_name
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
                Some(Ok(RpcMessage::Notification(_))) => {
                    // Ignore notifications (diagnostics, progress, etc)
                }
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

    // 2. Resolve Output Path
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

    // 3. Start Rust Analyzer
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
        while let Ok(Some(_line)) = lines.next_line().await {
            // Optional logging
        }
    });

    let stdin = process.stdin.take().unwrap();
    let stdout = process.stdout.take().unwrap();

    let mut client = LspClient {
        stdin: FramedWrite::new(stdin, LspCodec),
        stdout: FramedRead::new(BufReader::new(stdout), LspCodec),
        req_id: AtomicUsize::new(1),
    };

    // 4. Initialize LSP
    eprintln!("🤝 Initializing LSP...");
    let init_params = InitializeParams {
        process_id: Some(std::process::id()),
        root_uri: Some(root_uri.clone()),
        capabilities: ClientCapabilities {
            text_document: Some(TextDocumentClientCapabilities {
                document_symbol: Some(DocumentSymbolClientCapabilities {
                    hierarchical_document_symbol_support: Some(true),
                    ..Default::default()
                }),
                call_hierarchy: Some(lsp_types::CallHierarchyClientCapabilities {
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

    // 5. Gather Files & Content
    eprintln!("📂 Scanning for .rs files...");
    let mut files_to_scan = Vec::new();
    scan_files_recursive(&project_root, &mut files_to_scan);
    
    files_to_scan.retain(|p| {
        !p.components().any(|c| c.as_os_str() == "target" || c.as_os_str().to_string_lossy().starts_with('.'))
    });

    eprintln!("   Found {} rust files to analyze.", files_to_scan.len());
    
    let mut file_map: HashMap<Url, String> = HashMap::new();

    // 6. Open Files
    for path in &files_to_scan {
        let content = tokio::fs::read_to_string(path).await?;
        let uri = Url::from_file_path(path).map_err(|_| anyhow!("Invalid file path"))?;
        
        // Store for extraction
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

    // 8. Build Graph
    let mut graph = FdepGraph::new();
    let mut call_hierarchy_candidates = Vec::new();

    eprintln!("🏗️  Building Symbol Graph...");

    for (idx, path) in files_to_scan.iter().enumerate() {
        let uri = Url::from_file_path(path).unwrap();
        let relative_name = path.strip_prefix(&project_root).unwrap_or(path).to_string_lossy();
        
        eprint!("\r   [{}/{}] Analyzing: {}", idx + 1, files_to_scan.len(), relative_name);
        
        let mut attempts = 0;
        let mut found_symbols = false;
        
        let current_file_content = file_map.get(&uri).expect("File content missing from map");

        while attempts < 3 {
            attempts += 1;
            
            let params = DocumentSymbolParams {
                text_document: TextDocumentIdentifier { uri: uri.clone() },
                work_done_progress_params: Default::default(),
                partial_result_params: Default::default(),
            };

            match client.send_request("textDocument/documentSymbol", params).await {
                Ok(val) => {
                    if val.is_null() {
                        sleep(Duration::from_millis(500)).await;
                        continue;
                    }

                    let symbols: Result<Vec<DocumentSymbol>, _> = serde_json::from_value(val.clone());
                    match symbols {
                        Ok(syms) => {
                            if syms.is_empty() {
                                sleep(Duration::from_millis(200)).await;
                                continue;
                            }
                            for sym in syms {
                                process_symbol(
                                    &mut graph, 
                                    &mut call_hierarchy_candidates, 
                                    sym, 
                                    path, 
                                    &uri, 
                                    &project_root,
                                    current_file_content 
                                );
                            }
                            found_symbols = true;
                            break; 
                        }
                        Err(_) => { break; }
                    }
                }
                Err(_) => { break; }
            }
        }
    }

    eprintln!("\n🔗 Calculating Edges (Call Hierarchy)...");
    let total = call_hierarchy_candidates.len();
    let mut edges_count = 0;

    for (i, (node_id, uri, pos)) in call_hierarchy_candidates.into_iter().enumerate() {
        if i % 10 == 0 { eprint!("\r   {}/{}...", i, total); }

        let prep_params = lsp_types::CallHierarchyPrepareParams {
            text_document_position_params: lsp_types::TextDocumentPositionParams {
                text_document: TextDocumentIdentifier { uri: uri.clone() },
                position: pos,
            },
            work_done_progress_params: Default::default(),
        };

        if let Ok(val) = client.send_request("textDocument/prepareCallHierarchy", prep_params).await {
             let items: Option<Vec<CallHierarchyItem>> = serde_json::from_value(val).unwrap_or(None);
             if let Some(items) = items {
                 if let Some(root_item) = items.first() {
                     
                     // INCOMING
                     let in_params = CallHierarchyIncomingCallsParams {
                         item: root_item.clone(),
                         work_done_progress_params: Default::default(),
                         partial_result_params: Default::default(),
                     };
                     if let Ok(in_val) = client.send_request("callHierarchy/incomingCalls", in_params).await {
                         let calls: Option<Vec<CallHierarchyIncomingCall>> = serde_json::from_value(in_val).unwrap_or(None);
                         if let Some(calls) = calls {
                             for call in calls {
                                 // NEW ID LOGIC: relative_path::function_name
                                 let caller_id = generate_relative_id(&call.from.uri, &call.from.name, &project_root);
                                 graph.edges.push((caller_id, node_id.clone()));
                                 edges_count += 1;
                             }
                         }
                     }
                     
                     // OUTGOING
                     let out_params = CallHierarchyOutgoingCallsParams {
                         item: root_item.clone(),
                         work_done_progress_params: Default::default(),
                         partial_result_params: Default::default(),
                     };
                     if let Ok(out_val) = client.send_request("callHierarchy/outgoingCalls", out_params).await {
                         let calls: Option<Vec<CallHierarchyOutgoingCall>> = serde_json::from_value(out_val).unwrap_or(None);
                         if let Some(calls) = calls {
                             for call in calls {
                                 // NEW ID LOGIC: relative_path::function_name
                                 let callee_id = generate_relative_id(&call.to.uri, &call.to.name, &project_root);
                                 graph.edges.push((node_id.clone(), callee_id));
                                 edges_count += 1;
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
            if path.is_dir() {
                scan_files_recursive(&path, list);
            } else if path.extension().map_or(false, |e| e == "rs") {
                list.push(path);
            }
        }
    }
}

fn process_symbol(
    graph: &mut FdepGraph, 
    candidates: &mut Vec<(String, Url, Position)>,
    sym: DocumentSymbol, 
    file_path: &PathBuf, 
    uri: &Url,
    root: &PathBuf,
    content: &str
) {
    // Generate ID: relative_path::function_name
    let id = generate_relative_id(uri, &sym.name, root);
    
    let kind = match sym.kind {
        SymbolKind::FUNCTION | SymbolKind::METHOD | SymbolKind::CONSTRUCTOR => NodeType::Function,
        SymbolKind::STRUCT => NodeType::Struct,
        SymbolKind::ENUM => NodeType::Enum,
        SymbolKind::INTERFACE => NodeType::Interface,
        SymbolKind::CONSTANT => NodeType::Constant,
        SymbolKind::VARIABLE => NodeType::Variable,
        SymbolKind::MODULE => NodeType::Module,
        _ => NodeType::Unknown,
    };

    let relative = file_path.strip_prefix(root).unwrap_or(file_path).to_string_lossy().to_string();
    let extracted_code = extract_code(content, sym.range);

    graph.nodes.insert(id.clone(), GraphNode {
        id: id.clone(),
        label: sym.name.clone(),
        relative_path: relative, // Kept this
        node_type: kind.clone(),
        range: sym.selection_range,
        code: extracted_code, 
    });

    if matches!(kind, NodeType::Function) {
        candidates.push((id, uri.clone(), sym.selection_range.start));
    }

    if let Some(children) = sym.children {
        for child in children {
            process_symbol(graph, candidates, child, file_path, uri, root, content);
        }
    }
}

fn extract_code(content: &str, range: Range) -> String {
    let start_line = range.start.line as usize;
    let end_line = range.end.line as usize;
    
    content.lines()
        .skip(start_line)
        .take(end_line - start_line + 1)
        .collect::<Vec<&str>>()
        .join("\n")
}

// Updated Helper: Uses Project Root to calculate relative path
fn generate_relative_id(uri: &Url, name: &str, root: &Path) -> String {
    if let Ok(path) = uri.to_file_path() {
        let relative = path.strip_prefix(root).unwrap_or(&path).to_string_lossy();
        format!("{}::{}", relative, name)
    } else {
        format!("unknown::{}", name)
    }
}