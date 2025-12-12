use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub enum NodeType {
    Function,
    Class, // For struct/enum in Rust context
    Type,  // For type aliases, traits
    Module,
    Constant,
    Variable, // For static, const, or local variables
    Unknown,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GraphNode {
    pub id: String,
    pub file: String,
    pub label: String,
    pub code: String,
    pub signature: Option<String>, // Function signature or type definition
    pub node_type: NodeType,
    pub types_used: Vec<String>,
    pub depends_on: Vec<String>,
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
        if source_id != target_id {
            self.edges.push((source_id, target_id));
        }
    }
}
