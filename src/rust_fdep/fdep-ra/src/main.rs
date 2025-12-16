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
    pub id: String,
    pub label: String,
    pub file_path: String,
    pub relative_path: String, 
    pub node_type: NodeType,
    pub range: Range,
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
    let raw_output_path = args.get(2).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("call_graph.json"));

    // 1. Resolve Project Root
    let project_root = find_cargo_toml(&raw_project_path)
        .ok_or_else(|| anyhow!("Could not find Cargo.toml in {:?} or parents", raw_project_path))?
        .canonicalize()?; // IMPORTANT: Canonicalize to resolve symlinks/relative paths
    
    eprintln!("📍 Resolved Project Root: {:?}", project_root);

    // 2. Resolve Output Path
    let output_path = if raw_output_path.is_dir() {
        raw_output_path.join("call_graph.json")
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
        while let Ok(Some(line)) = lines.next_line().await {
            // OPTIONAL: Uncomment to see what RA is doing internally
            // if line.contains("error") { eprintln!("[RA-ERR] {}", line); }
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

    // 5. Gather Files
    eprintln!("📂 Scanning for .rs files...");
    let mut files_to_scan = Vec::new();
    scan_files_recursive(&project_root, &mut files_to_scan);
    
    // Filter to avoid target/ and hidden files
    files_to_scan.retain(|p| {
        !p.components().any(|c| c.as_os_str() == "target" || c.as_os_str().to_string_lossy().starts_with('.'))
    });

    eprintln!("   Found {} rust files to analyze.", files_to_scan.len());
    
    // 6. Open Files
    for path in &files_to_scan {
        let content = tokio::fs::read_to_string(path).await?;
        let uri = Url::from_file_path(path).map_err(|_| anyhow!("Invalid file path"))?;
        
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

    // 7. Initial Warmup (Poll for readiness)
    eprintln!("⏳ Waiting for RA to warm up...");
    // We give it a moment to register the DidOpen
    sleep(Duration::from_secs(2)).await;

    // 8. Build Graph (With RETRY Logic)
    let mut graph = FdepGraph::new();
    let mut call_hierarchy_candidates = Vec::new();

    eprintln!("🏗️  Building Symbol Graph (Attempting to fetch symbols)...");

    for (idx, path) in files_to_scan.iter().enumerate() {
        let uri = Url::from_file_path(path).unwrap();
        let relative_name = path.strip_prefix(&project_root).unwrap_or(path).to_string_lossy();
        
        eprint!("\r   [{}/{}] Analyzing: {}", idx + 1, files_to_scan.len(), relative_name);
        
        // RETRY LOOP: Try up to 3 times per file if we get empty results
        let mut attempts = 0;
        let mut found_symbols = false;

        while attempts < 3 {
            attempts += 1;
            
            let params = DocumentSymbolParams {
                text_document: TextDocumentIdentifier { uri: uri.clone() },
                work_done_progress_params: Default::default(),
                partial_result_params: Default::default(),
            };

            match client.send_request("textDocument/documentSymbol", params).await {
                Ok(val) => {
                    // Check if null
                    if val.is_null() {
                        // RA not ready, wait and retry
                        sleep(Duration::from_millis(500)).await;
                        continue;
                    }

                    // Try parsing
                    let symbols: Result<Vec<DocumentSymbol>, _> = serde_json::from_value(val.clone());
                    match symbols {
                        Ok(syms) => {
                            if syms.is_empty() {
                                // Empty is suspicious for a non-empty file, retry shortly
                                sleep(Duration::from_millis(200)).await;
                                continue;
                            }
                            // SUCCESS
                            for sym in syms {
                                process_symbol(&mut graph, &mut call_hierarchy_candidates, sym, path, &uri, &project_root);
                            }
                            found_symbols = true;
                            break; 
                        }
                        Err(_) => {
                            // Might be SymbolInformation[] (flat) instead of DocumentSymbol[] (nested)
                            // For now, we assume nested because we requested it. 
                            eprintln!("\n   ⚠️  Response format error for {}: {:?}", relative_name, val);
                            break;
                        }
                    }
                }
                Err(e) => {
                    eprintln!("\n   ⚠️  LSP Error for {}: {}", relative_name, e);
                    break;
                }
            }
        }
        
        if !found_symbols {
             // Just a debug marker, not necessarily a failure (file might genuinely be empty of symbols)
             // eprintln!(" -> No symbols found."); 
        }
    }

    eprintln!("\n🔗 Calculating Edges (Call Hierarchy)...");
    eprintln!("   Candidates to analyze: {}", call_hierarchy_candidates.len());

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
                                 let caller_id = generate_id(&call.from.uri, call.from.selection_range);
                                 // Add edge if caller exists in our node list (optional filter)
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
                                 let callee_id = generate_id(&call.to.uri, call.to.selection_range);
                                 graph.edges.push((node_id.clone(), callee_id));
                                 edges_count += 1;
                             }
                         }
                     }
                 }
             }
        }
    }

    // 9. Save
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
    root: &PathBuf
) {
    let id = generate_id(uri, sym.selection_range);
    
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

    graph.nodes.insert(id.clone(), GraphNode {
        id: id.clone(),
        label: sym.name.clone(),
        file_path: file_path.to_string_lossy().to_string(),
        relative_path: relative,
        node_type: kind.clone(),
        range: sym.selection_range,
    });

    // Only candidates for Call Hierarchy are functions
    if matches!(kind, NodeType::Function) {
        candidates.push((id, uri.clone(), sym.selection_range.start));
    }

    if let Some(children) = sym.children {
        for child in children {
            process_symbol(graph, candidates, child, file_path, uri, root);
        }
    }
}

fn generate_id(uri: &Url, range: Range) -> String {
    format!("{}::{}:{}", uri.path(), range.start.line, range.start.character)
}