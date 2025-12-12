use std::env;
use std::path::PathBuf;
use std::process::Stdio;
use std::collections::HashMap;
use std::str::FromStr;

use anyhow::{anyhow, Result, Context};
use futures::{SinkExt, StreamExt};
use lsp_types::{
    InitializeParams, InitializeResult, InitializedParams, 
    TextDocumentItem, DidOpenTextDocumentParams, DocumentSymbolParams, TextDocumentIdentifier,
    DocumentSymbolResponse, Url, DocumentSymbol, SymbolKind,
    Position, CallHierarchyItem, CallHierarchyIncomingCallsParams, CallHierarchyOutgoingCallsParams,
    CallHierarchyIncomingCall, CallHierarchyOutgoingCall, WorkspaceFolder, Range
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::io::BufReader;
use tokio::process::Command;
use tokio_util::codec::{Decoder, Encoder, FramedRead, FramedWrite};
use bytes::{BytesMut, Buf};

// --- 1. Custom LSP Codec (CRITICAL FIX) ---
// LSP uses "Content-Length: <num>\r\n\r\n" headers.

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
        // 1. Find the double newline separating headers from body
        if let Some(i) = src.windows(4).position(|b| b == b"\r\n\r\n") {
            let headers_bytes = &src[..i];
            let headers_str = std::str::from_utf8(headers_bytes)?;
            
            // 2. Parse Content-Length
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
                .ok_or_else(|| anyhow!("Missing or invalid Content-Length header"))?;

            // 3. Check if we have enough bytes for the body
            let total_len = i + 4 + content_len;
            if src.len() < total_len {
                return Ok(None); // Wait for more data
            }

            // 4. Consume headers
            src.advance(i + 4);
            
            // 5. Consume body
            let body_bytes = src.split_to(content_len);
            let msg: RpcMessage = serde_json::from_slice(&body_bytes)?;
            
            return Ok(Some(msg));
        }
        Ok(None)
    }
}

// --- JSON-RPC Envelopes ---

#[derive(Serialize, Deserialize, Debug)]
struct RpcRequest {
    jsonrpc: String,
    id: usize,
    method: String,
    params: Value,
}

#[derive(Serialize, Deserialize, Debug)]
struct RpcResponse {
    jsonrpc: String,
    id: usize,
    result: Option<Value>,
    error: Option<Value>,
}

#[derive(Serialize, Deserialize, Debug)]
struct RpcNotification {
    jsonrpc: String,
    method: String,
    params: Value,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(untagged)]
enum RpcMessage {
    Response(RpcResponse),
    Request(RpcRequest),
    Notification(RpcNotification),
}

impl RpcMessage {
    fn new_request(id: usize, method: &str, params: Value) -> Self {
        RpcMessage::Request(RpcRequest {
            jsonrpc: "2.0".to_string(),
            id,
            method: method.to_string(),
            params,
        })
    }

    fn new_notification(method: &str, params: Value) -> Self {
        RpcMessage::Notification(RpcNotification {
            jsonrpc: "2.0".to_string(),
            method: method.to_string(),
            params,
        })
    }
}

// --- Graph Structures ---

#[derive(Debug, Serialize, Deserialize, Clone)]
pub enum NodeType {
    Function,
    Class,
    Type,
    Module,
    Constant,
    Variable, 
    Unknown,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GraphNode {
    pub id: String,
    pub file: String,
    pub label: String,
    pub code: String,
    pub signature: Option<String>, 
    pub node_type: NodeType,
    pub range: Range, // Store range for debugging/UI
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

    pub fn add_node(&mut self, node: GraphNode) {
        self.nodes.insert(node.id.clone(), node);
    }

    pub fn add_edge(&mut self, source_id: String, target_id: String) {
        // Prevent self-loops if desired, but self-recursion is valid
        if source_id != target_id {
            // Avoid duplicates
            if !self.edges.contains(&(source_id.clone(), target_id.clone())) {
                self.edges.push((source_id, target_id));
            }
        }
    }
}

// --- Helper Functions ---

// FIX: Generate ID based on File + Line:Col. 
// This allows DocumentSymbol and CallHierarchyItem to produce the exact same ID.
fn get_node_id(file_uri: &Url, range: Range) -> String {
    format!("{}::{}:{}", file_uri.path(), range.start.line, range.start.character)
}

async fn get_code_snippet(file_path: &str, start_line: usize, end_line: usize) -> Result<String> {
    // Basic error handling for file reading
    let content = match tokio::fs::read_to_string(file_path).await {
        Ok(c) => c,
        Err(_) => return Ok("".to_string()),
    };
    let lines: Vec<&str> = content.lines().collect();

    if start_line <= end_line && end_line < lines.len() {
        Ok(lines[start_line..=end_line].join("\n"))
    } else if start_line < lines.len() && start_line == end_line {
        Ok(lines[start_line].to_string())
    } else {
        Ok("".to_string())
    }
}

fn convert_symbol_kind(k: SymbolKind) -> NodeType {
    match k {
        SymbolKind::FUNCTION | SymbolKind::METHOD | SymbolKind::CONSTRUCTOR => NodeType::Function,
        SymbolKind::CLASS | SymbolKind::STRUCT | SymbolKind::ENUM | SymbolKind::INTERFACE => NodeType::Class,
        SymbolKind::MODULE => NodeType::Module,
        SymbolKind::CONSTANT => NodeType::Constant,
        SymbolKind::VARIABLE => NodeType::Variable,
        SymbolKind::TYPE_PARAMETER => NodeType::Type,
        _ => NodeType::Unknown,
    }
}

// --- Main Analysis Logic ---

#[tokio::main]
async fn main() -> Result<()> {
    eprintln!("Hooray");
    env_logger::init();

    let args: Vec<String> = env::args().collect();
    let project_path_arg = args.get(1).map(PathBuf::from).ok_or_else(|| anyhow!("Project path argument missing"))?;
    let output_dir = args.get(2).map(PathBuf::from).ok_or_else(|| anyhow!("Output directory argument missing"))?;

    eprintln!("🦀 Rust dependency analyzer starting...");
    
    // 1. Get Metadata
    let metadata = cargo_metadata::MetadataCommand::new()
        .current_dir(&project_path_arg)
        .exec()?;
    let workspace_root = metadata.workspace_root.into_std_path_buf();
    let root_uri = Url::from_directory_path(&workspace_root).unwrap();

    // 2. Launch rust-analyzer
    eprintln!("🚀 Starting rust-analyzer...");
    let mut child = Command::new("rust-analyzer")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped()) 
        .spawn()
        .context("Failed to start rust-analyzer")?;

    let stdin = child.stdin.take().unwrap();
    let stdout = child.stdout.take().unwrap();

    // USE CUSTOM LSP CODEC
    let mut stdin_framed = FramedWrite::new(stdin, LspCodec);
    let mut stdout_framed = FramedRead::new(BufReader::new(stdout), LspCodec);

    // 3. Initialize LSP
    let initialize_params = InitializeParams {
        process_id: Some(std::process::id()),
        workspace_folders: Some(vec![WorkspaceFolder {
            uri: root_uri.clone(),
            name: "root".to_string(),
        }]),
        root_uri: None, 
        capabilities: lsp_types::ClientCapabilities {
            text_document: Some(lsp_types::TextDocumentClientCapabilities {
                call_hierarchy: Some(lsp_types::CallHierarchyClientCapabilities {
                    dynamic_registration: Some(false), 
                }),
                document_symbol: Some(lsp_types::DocumentSymbolClientCapabilities {
                    dynamic_registration: Some(false),
                    hierarchical_document_symbol_support: Some(true), 
                    ..Default::default()
                }),
                ..Default::default()
            }),
            ..Default::default()
        },
        trace: Some(lsp_types::TraceValue::Verbose),
        client_info: Some(lsp_types::ClientInfo {
            name: "fdep-ra-client".to_string(),
            version: Some("0.1.0".to_string()),
        }),
        ..Default::default()
    };

    let init_req = RpcMessage::new_request(1, "initialize", serde_json::to_value(&initialize_params)?);
    send_message(&mut stdin_framed, init_req).await?;

    // Wait for Init Response
    loop {
        match stdout_framed.next().await {
            Some(Ok(RpcMessage::Response(resp))) if resp.id == 1 => {
                log::info!("Initialized.");
                break;
            }
            Some(Ok(msg)) => log::debug!("Ignored during init: {:?}", msg),
            Some(Err(e)) => return Err(anyhow!("Transport error: {}", e)),
            None => return Err(anyhow!("Stream ended")),
        }
    }

    let initialized_notif = RpcMessage::new_notification("initialized", serde_json::to_value(&InitializedParams {})?);
    send_message(&mut stdin_framed, initialized_notif).await?;

    // --- Start Graph Building ---

    let mut fdep_graph = FdepGraph::new();
    let mut file_uris = Vec::new(); 
    // Store (ID, Uri, Position) for functions we want to inspect later
    let mut callable_nodes_for_ch: Vec<(String, Url, Position)> = Vec::new();

    // 4. Open Documents
    for package in &metadata.packages {
        for target in &package.targets {
            if target.kind.iter().any(|k| k == "lib" || k == "bin" || k == "proc-macro") {
                let src_path = target.src_path.clone().into_std_path_buf();
                if src_path.exists() && src_path.extension().map_or(false, |ext| ext == "rs") {
                    let file_content = tokio::fs::read_to_string(&src_path).await?;
                    let file_uri = Url::from_file_path(&src_path).unwrap();
                    file_uris.push(file_uri.clone());

                    let did_open_params = DidOpenTextDocumentParams {
                        text_document: TextDocumentItem {
                            uri: file_uri.clone(),
                            language_id: "rust".to_string(),
                            version: 1,
                            text: file_content,
                        },
                    };
                    let notif = RpcMessage::new_notification("textDocument/didOpen", serde_json::to_value(&did_open_params)?);
                    send_message(&mut stdin_framed, notif).await?;
                }
            }
        }
    }

    // Give RA a split second to index the new files
    tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;

    // 5. Get Document Symbols
    let mut req_id_counter = 2; 
    let total_files = file_uris.len();
    
    for (file_index, uri) in file_uris.iter().enumerate() {
        eprint!("\r🔍 Analyzing file {}/{}", file_index + 1, total_files);
        let params = DocumentSymbolParams {
            text_document: TextDocumentIdentifier { uri: uri.clone() },
            work_done_progress_params: Default::default(),
            partial_result_params: Default::default(),
        };

        let req = RpcMessage::new_request(req_id_counter, "textDocument/documentSymbol", serde_json::to_value(&params)?);
        send_message(&mut stdin_framed, req).await?;
        let current_req_id = req_id_counter;
        req_id_counter += 1;

        loop {
            match stdout_framed.next().await {
                Some(Ok(RpcMessage::Response(resp))) if resp.id == current_req_id => {
                    let res_val = resp.result.unwrap_or(Value::Null);
                    let symbols_response: Option<DocumentSymbolResponse> = serde_json::from_value(res_val)?;
                    
                    if let Some(symbols_response) = symbols_response {
                         match symbols_response {
                            DocumentSymbolResponse::Flat(sis) => {
                                for si in sis {
                                    // Note: Flat structure is rare in RA for symbols, usually Nested
                                    // Logic omitted for brevity, similar to nested below but simpler
                                }
                            }
                            DocumentSymbolResponse::Nested(dss) => {
                                for ds in dss {
                                    add_nested_symbols_to_graph(&mut fdep_graph, uri, ds, &mut callable_nodes_for_ch).await?;
                                }
                            }
                        }
                    }
                    break;
                }
                Some(Ok(_)) => {}, // skip notifications
                Some(Err(e)) => return Err(e),
                None => return Err(anyhow!("Connection closed")),
            }
        }
    }
    eprintln!("\n✅ Symbol analysis complete.");

    // 6. Call Hierarchy
    let total_functions = callable_nodes_for_ch.len();
    let mut func_processed = 0;
    
    for (node_id, uri, position) in callable_nodes_for_ch {
        func_processed += 1;
        if func_processed % 10 == 0 {
             eprint!("\r🔗 Analyzing call hierarchy {}/{}", func_processed, total_functions);
        }

        // A. Prepare Call Hierarchy
        let prepare_params = lsp_types::CallHierarchyPrepareParams {
            text_document_position_params: lsp_types::TextDocumentPositionParams {
                text_document: TextDocumentIdentifier { uri: uri.clone() },
                position,
            },
            work_done_progress_params: Default::default(),
        };

        send_message(&mut stdin_framed, RpcMessage::new_request(req_id_counter, "textDocument/prepareCallHierarchy", serde_json::to_value(&prepare_params)?)).await?;
        let prep_id = req_id_counter;
        req_id_counter += 1;

        let mut item: Option<CallHierarchyItem> = None;

        // Loop for Prepare Response
        loop {
            match stdout_framed.next().await {
                Some(Ok(RpcMessage::Response(resp))) if resp.id == prep_id => {
                    let res: Option<Vec<CallHierarchyItem>> = serde_json::from_value(resp.result.unwrap_or(Value::Null))?;
                    if let Some(items) = res {
                        if !items.is_empty() {
                            item = Some(items[0].clone());
                        }
                    }
                    break;
                }
                Some(Ok(_)) => {},
                Some(Err(e)) => return Err(e),
                None => break,
            }
        }

        if let Some(root_item) = item {
            // B. Incoming Calls
            let in_params = CallHierarchyIncomingCallsParams {
                item: root_item.clone(),
                work_done_progress_params: Default::default(),
                partial_result_params: Default::default(),
            };
            send_message(&mut stdin_framed, RpcMessage::new_request(req_id_counter, "callHierarchy/incomingCalls", serde_json::to_value(&in_params)?)).await?;
            let in_id = req_id_counter;
            req_id_counter += 1;

            loop {
                match stdout_framed.next().await {
                     Some(Ok(RpcMessage::Response(resp))) if resp.id == in_id => {
                        let calls: Option<Vec<CallHierarchyIncomingCall>> = serde_json::from_value(resp.result.unwrap_or(Value::Null))?;
                        if let Some(calls) = calls {
                            for call in calls {
                                // IMPORTANT: Use range-based ID to ensure we hit the node created by DocumentSymbol
                                let caller_id = get_node_id(&call.from.uri, call.from.selection_range);
                                fdep_graph.add_edge(caller_id, node_id.clone());
                            }
                        }
                        break;
                     }
                     Some(Ok(_)) => {},
                     Some(Err(_)) => break,
                     None => break,
                }
            }

            // C. Outgoing Calls (Similar logic)
            let out_params = CallHierarchyOutgoingCallsParams {
                item: root_item.clone(),
                work_done_progress_params: Default::default(),
                partial_result_params: Default::default(),
            };
            send_message(&mut stdin_framed, RpcMessage::new_request(req_id_counter, "callHierarchy/outgoingCalls", serde_json::to_value(&out_params)?)).await?;
            let out_id = req_id_counter;
            req_id_counter += 1;
            
            loop {
                match stdout_framed.next().await {
                     Some(Ok(RpcMessage::Response(resp))) if resp.id == out_id => {
                        let calls: Option<Vec<CallHierarchyOutgoingCall>> = serde_json::from_value(resp.result.unwrap_or(Value::Null))?;
                        if let Some(calls) = calls {
                            for call in calls {
                                let callee_id = get_node_id(&call.to.uri, call.to.selection_range);
                                fdep_graph.add_edge(node_id.clone(), callee_id);
                            }
                        }
                        break;
                     }
                     Some(Ok(_)) => {},
                     _ => break,
                }
            }
        }
    }

    eprintln!("\n✅ Shutting down...");
    send_message(&mut stdin_framed, RpcMessage::new_request(req_id_counter, "shutdown", Value::Null)).await?;
    // Wait for shutdown response... then exit
    let _ = stdout_framed.next().await;
    send_message(&mut stdin_framed, RpcMessage::new_notification("exit", Value::Null)).await?;

    // Save
    let output_file_path = output_dir.join("fdep-output.json");
    tokio::fs::write(&output_file_path, serde_json::to_string_pretty(&fdep_graph)?).await?;
    eprintln!("Done! Graph saved to {}", output_file_path.display());

    Ok(())
}

async fn send_message(
    sink: &mut FramedWrite<tokio::process::ChildStdin, LspCodec>,
    msg: RpcMessage,
) -> Result<()> {
    sink.send(msg).await?;
    Ok(())
}

async fn add_nested_symbols_to_graph(
    fdep_graph: &mut FdepGraph,
    file_uri: &Url,
    document_symbol: DocumentSymbol,
    callable_nodes: &mut Vec<(String, Url, Position)>,
) -> Result<()> {
    let file_path = file_uri.to_file_path().unwrap().to_string_lossy().to_string();
    let node_type = convert_symbol_kind(document_symbol.kind);
    
    // Use SELECTION RANGE for accurate ID mapping with Call Hierarchy
    let unique_id = get_node_id(file_uri, document_symbol.selection_range);

    let code_snippet = get_code_snippet(&file_path, document_symbol.range.start.line as usize, document_symbol.range.end.line as usize).await?;

    fdep_graph.add_node(GraphNode {
        id: unique_id.clone(),
        file: file_path.clone(),
        label: document_symbol.name.clone(),
        code: code_snippet,
        signature: document_symbol.detail.clone(),
        node_type: node_type.clone(),
        range: document_symbol.selection_range,
    });

    if matches!(node_type, NodeType::Function) {
        // We use selection_range.start for the position argument in prepareCallHierarchy
        callable_nodes.push((unique_id.clone(), file_uri.clone(), document_symbol.selection_range.start));
    }

    if let Some(children) = document_symbol.children {
        for child in children {
            Box::pin(add_nested_symbols_to_graph(fdep_graph, file_uri, child, callable_nodes)).await?;
        }
    }

    Ok(())
}