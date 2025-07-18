# CODETRAVERSE

**CODETRAVERSE** is a cross-language static code analysis tool that extracts structural components and dependencies from code repositories in Haskell, Rescript, Typescript, Rust, golang, python, purescript.

Given any supported codebase, CODETRAVERSE outputs:
- Per-file JSON summaries (`fdep/`)
- Full call and type dependency graphs in **GraphML** and **gpickle** formats

This enables rich code visualization, impact analysis, dependency inspection, and more.

---

## 🚀 Features

- **Multi-language Support:** Haskell, Rescript, Typescript, Rust, golang, python, purescript (easily extensible!)
- **Scalable:** Handles arbitrarily nested folder structures
- **Rich Outputs:**
  - JSON component files for every source file
  - `repo_function_calls.graphml` (visual graph for tools like Gephi, yEd, etc.)
  - `repo_function_calls.gpickle` (Python-native NetworkX graph)
- **Graph Querying:** Use `path.py` to:
  - Find the shortest path between two components in the graph
  - List all direct neighbors (incoming and outgoing edges) for a given component

---

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone https://github.com/juspay/codetraverse.git
cd codetraverse
```

### 2. Install Dependencies
We recommend using a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate

# Install all required Python packages
pip install -r requirements.txt
```

---

## ⚡ Usage

### Basic Usage
```bash
python main.py --ROOT_DIR=/path/to/your/repo --LANGUAGE=golang
```

- Replace `/path/to/your/repo` with the root directory of your code repository
- Set `--LANGUAGE` to one of: `haskell`, `rescript`, `typescript`, `rust`, `golang`, `python`, `purescript`

Outputs will be saved in:
- `fdep/` (JSON component summaries)
- `graph/repo_function_calls.graphml`
- `graph/repo_function_calls.gpickle`

### All Options

| Argument | Type | Description |
|----------|------|-------------|
| `--ROOT_DIR` | str | Path to the root of the source code repository (required) |
| `--LANGUAGE` | str | One of `haskell`, `rescript`, `typescript`, `rust`, `golang`, `python`,`purescript` (required) |
| `--OUTPUT_BASE` (opt) | str | Output directory for per-file JSONs (default: `fdep`) |
| `--GRAPH_DIR`  (opt) | str | Output directory for the graphs (default: `graph`) |

### Example
```bash
python main.py --ROOT_DIR =/my-go-project --LANGUAGE=golang
```

---
## ⚡ Graph Path Usage

### Querying the Graph with `path.py`

Use `path.py` to query the generated graph for relationships between components.

#### Find the Shortest Path Between Two Components
```bash
python path.py --GRAPH_PATH=/path/to/repo_function_calls.graphml --COMPONENT=<target_component> --SOURCE=<source_component>
```

- Replace `/path/to/repo_function_calls.graphml` with the path to your graph file.
- Replace `<target_component>` with the fully-qualified ID of the target component (e.g., `PgIntegrationApp::make`).
- Replace `<source_component>` with the fully-qualified ID of the source component.

Example:
```bash
python path.py --GRAPH_PATH=graph/repo_function_calls.graphml --COMPONENT=PgIntegrationApp::make --SOURCE=PgIntegrationApp::init
```

#### List Direct Neighbors of a Component
```bash
python path.py --GRAPH_PATH=/path/to/repo_function_calls.graphml --COMPONENT=<target_component>
```

- Replace `/path/to/repo_function_calls.graphml` with the path to your graph file.
- Replace `<target_component>` with the fully-qualified ID of the target component.

Example:
```bash
python path.py --GRAPH_PATH=graph/repo_function_calls.graphml --COMPONENT=PgIntegrationApp::make
```

---

### All Options

| Argument       | Type | Description                                                                 |
|----------------|------|-----------------------------------------------------------------------------|
| `--GRAPH_PATH` or `-g`| str  | Path to the saved graph (`.gpickle` or `.graphml`)                          |
| `--COMPONENT` or `-c` | str  | Target fully-qualified component ID (e.g., `PgIntegrationApp::make`)        |
| `--SOURCE`  or `-s`   | str  | (Optional) Source fully-qualified ID. If omitted, lists direct neighbors.   |

---

### Output Examples

#### Shortest Path
If a path exists between the source and target components, the output will look like:
```
Shortest path from 'PgIntegrationApp::init' → 'PgIntegrationApp::make':
  PgIntegrationApp::init → PgIntegrationApp::process → PgIntegrationApp::make
```

#### Direct Neighbors
If listing direct neighbors, the output will show incoming and outgoing edges:
```
Nodes with edges INTO 'PgIntegrationApp::make' (2):
  PgIntegrationApp::process --[calls]--> PgIntegrationApp::make
  PgIntegrationApp::init --[calls]--> PgIntegrationApp::make

Nodes with edges OUT OF 'PgIntegrationApp::make' (1):
  PgIntegrationApp::make --[uses_type]--> PgIntegrationApp::ResultType
```


## 🔍 How it Works

1. **Extract:** Recursively walks your codebase, parsing each file, extracting functions, types, variables, dependencies, etc.

2. **Component Output:** For every file, generates a detailed `.json` file in the `fdep/` directory.

3. **Unification and Graph Construction:** Merges all components into a single global call/type graph using NetworkX.

4. **Export:** Writes the graph to:
   - `repo_function_calls.graphml` (portable to any graph tool)
   - `repo_function_calls.gpickle` (for Python/NetworkX use)

---

## 🗂️ Output Files

### `fdep/`
Per-source-file JSONs, containing extracted component data.

### `graph/repo_function_calls.graphml`
Universal call/type dependency graph in GraphML (XML) format.

### `graph/repo_function_calls.gpickle`
NetworkX-serialized Python object for fast downstream analysis.

---


## ❓ FAQ

**Q: Does this overwrite my source code?**
A: No. All outputs are written to `fdep/` and `graph/`.

**Q: Can I use this for closed-source or private code?**
A: Yes! All code runs locally.

**Q: What if I want to re-run and overwrite outputs?**
A: Just `rm -rf fdep graph` before running again.

**Q: What if I want to visualize the graph?**
A: Use Gephi, yEd, or any tool that supports GraphML.


---
