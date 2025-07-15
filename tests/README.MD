## CodeTraverse: Testing Guide

This document outlines the process for generating FDEP JSON and GraphML files, running tests locally, and setting up Continuous Integration (CI) for multiple programming languages within the CodeTraverse project.

---

### 1. Generate FDEP & GraphML (Local)

To extract components and build call-graphs for each sample repository, run the following command from your project root:

```bash
for sd in sample_code_repo_test/*; do
  lang=$(basename "$sd")
  echo "→ Generating for $lang…"
  python scripts/generate_tests_fdep_graph.py \
    --root-dir  "sample_code_repo_test/$lang" \
    --out-fdep  "output/fdep/$lang" \
    --out-graph "output/graph/$lang"
done
```

This process will generate the following output files:

```
output/fdep/<lang>/*.json
output/graph/<lang>/*.graphml
```

---

### 2. Run Tests Locally

To execute tests for adapters and extractors, ensure your project is added to your `PYTHONPATH` and then run `pytest`:

```bash
export PYTHONPATH=.
pytest -v tests/adapters tests/extractors
```

---

### 3. CI Workflow

Integrate (or update) your CI workflow by adding the following content to `.github/workflows/component-tests.yml`:

```yaml
name: Run Component Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include:
          - name: go
            dir: golang
          - name: typescript
            dir: typescript
          - name: haskell
            dir: haskell
          - name: python
            dir: python
          # ----- new language name and dir here
```

---

### 4. Adding a New Language

To support a new language, follow these steps:

#### Sample Code

Create a directory `sample_code_repo_test/<lang>/` with the following files:

```
index.<ext>
utils.<ext>
models.<ext>
types.<ext>
```

Each file should include:

- A top-level variable/constant  
- A free function  
- A data-type (class/struct/interface)  
- A 4-step call chain: `index → utils → models → types`  
- All other features handled in the extractor and how they are managed in the adapter  

#### Generate Outputs

Re-run the script from Step 1 to generate the FDEP and GraphML outputs for your new language.

#### Write Tests

Create test files for your new language:

```
Extractor: tests/extractors/test_<lang>_extractor.py
Adapter: tests/adapters/test_<lang>_adapter.py
```

#### CI Matrix

Update `component-tests.yml` (as shown in Step 3) to add an entry for your new language under `matrix.include`.

#### Verify

Run `pytest` to ensure everything works as expected:

```bash
pytest -v
```

With these steps, your new language will be fully extracted, adapted, and tested on every push or pull request.
