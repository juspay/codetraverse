/**
 * Basic usage examples for the CodeTraverse Bridge
 * 
 * This file demonstrates how to use the bridge in a Node.js application
 */

const { CodeTraverseBridge } = require('../dist/index.js');

async function main() {
  // Create a bridge instance
  const bridge = new CodeTraverseBridge({
    pythonPath: 'python',  // or 'python3' on some systems
    timeout: 60000,        // 60 seconds timeout
  });

  try {
    // Validate that the bridge is set up correctly
    console.log('Validating CodeTraverse setup...');
    await bridge.validateSetup();
    console.log('✓ Setup is valid');

    // Example 1: Analyze a single TypeScript file
    console.log('\n--- Single File Analysis ---');
    try {
      const singleFileComponents = await bridge.analyzeFile(
        './examples/sample.ts',  // Replace with actual file path
        'typescript'
      );
      console.log(`Found ${singleFileComponents.length} components:`);
      singleFileComponents.forEach(comp => {
        console.log(`  - ${comp.kind}: ${comp.name} (${comp.full_component_path})`);
      });
    } catch (error) {
      console.log('Single file analysis skipped (file not found):', error.message);
    }

    // Example 2: Analyze a workspace
    console.log('\n--- Workspace Analysis ---');
    try {
      const workspaceData = await bridge.analyzeWorkspace('./src', {  // Replace with actual path
        language: 'typescript',
        outputBase: 'temp_fdep',
        graphDir: 'temp_graph'
      });
      console.log(`Workspace contains ${workspaceData.nodes.length} nodes and ${workspaceData.edges.length} edges`);
      
      // Show first few nodes
      console.log('Sample nodes:');
      workspaceData.nodes.slice(0, 3).forEach(node => {
        console.log(`  - ${node.id} (${node.category})`);
      });
    } catch (error) {
      console.log('Workspace analysis skipped:', error.message);
    }

    // Example 3: Get components from a workspace
    console.log('\n--- Component Extraction ---');
    try {
      const components = await bridge.analyzeWorkspaceComponents('./src', {
        language: 'typescript',
        outputBase: 'temp_fdep_comp',
        graphDir: 'temp_graph_comp'
      });
      console.log(`Found ${components.length} total components`);
      
      // Group by kind
      const byKind = components.reduce((acc, comp) => {
        acc[comp.kind] = (acc[comp.kind] || 0) + 1;
        return acc;
      }, {});
      
      console.log('Components by type:');
      Object.entries(byKind).forEach(([kind, count]) => {
        console.log(`  - ${kind}: ${count}`);
      });
    } catch (error) {
      console.log('Component extraction skipped:', error.message);
    }

    // Example 4: Query graph for paths (requires existing graph file)
    console.log('\n--- Graph Querying ---');
    try {
      const pathResult = await bridge.findPath(
        'temp_graph/repo_function_calls.graphml',
        'src/utils::helper',
        'src/main::main'
      );
      
      if (pathResult.found && pathResult.path) {
        console.log('Path found:', pathResult.path.join(' → '));
      } else {
        console.log('No path found between components');
      }
    } catch (error) {
      console.log('Path querying skipped:', error.message);
    }

    // Example 5: Get component neighbors
    try {
      const neighbors = await bridge.getNeighbors(
        'temp_graph/repo_function_calls.graphml',
        'src/main::main'
      );
      
      console.log(`Component has ${neighbors.incoming.length} incoming and ${neighbors.outgoing.length} outgoing connections`);
    } catch (error) {
      console.log('Neighbor querying skipped:', error.message);
    }

    // Show supported languages
    console.log('\n--- Supported Languages ---');
    const languages = bridge.getSupportedLanguages();
    console.log('Supported languages:', languages.join(', '));

  } catch (error) {
    console.error('Error:', error.message);
    if (error.code) {
      console.error('Error code:', error.code);
    }
    process.exit(1);
  }
}

// Handle unhandled promise rejections
process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
  process.exit(1);
});

if (require.main === module) {
  main().catch(console.error);
}

module.exports = { main };