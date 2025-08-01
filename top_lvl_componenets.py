
import os
import json
from codetraverse.utils.AstDifferOrchestrator import AstDiffOrchestrator

def extract_components_from_file(file_path: str):
    """
    Extract top-level components (classes, functions, etc.) from a single file.
    
    Args:
        file_path (str): Path to the source code file
        
    Returns:
        dict: Dictionary containing extracted components organized by type
    """
    
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    
    # Initialize the orchestrator
    orchestrator = AstDiffOrchestrator()
    
    # Check if the file type is supported
    if not orchestrator.is_supported(file_path):
        return {"error": f"Unsupported file type: {file_path}"}
    
    # Get the appropriate parser and differ for this file type
    parser = orchestrator.get_parser(file_path)
    differ = orchestrator.get_differ(file_path)
    
    if not parser or not differ:
        return {"error": f"Could not get parser/differ for: {file_path}"}
    
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the file into an AST
        ast = parser.parse(content.encode('utf-8'))
        
        # Extract components using the language-specific differ
        components = differ.extract_components(ast.root_node)
        
        # Convert to a more readable format
        result = {
            "file_path": file_path,
            "language": orchestrator.INVERSE_EXTS.get(orchestrator._get_extension(file_path), "unknown"),
            "components": {}
        }
        
        # Handle different return formats from different languages
        if isinstance(components, dict):
            # Some languages return a dict of component types
            for component_type, items in components.items():
                if items:  # Only include non-empty categories
                    result["components"][component_type] = []
                    for name, data in items.items():
                        # data is typically (node, text, start_point, end_point)
                        if isinstance(data, tuple) and len(data) >= 4:
                            result["components"][component_type].append({
                                "name": name,
                                "start_line": data[2][0] + 1,  # Convert 0-based to 1-based
                                "end_line": data[3][0] + 1,
                                "content": data[1],  # Full content instead of preview
                                "start_byte": data[2][1] if len(data[2]) > 1 else 0,
                                "end_byte": data[3][1] if len(data[3]) > 1 else 0
                            })
        elif isinstance(components, tuple):
            # Handle different language-specific tuple formats
            language = result["language"]
            
            if language == "haskell":
                # For Haskell: functions, data_types, type_classes, instances, imports, template_haskell
                component_names = ["functions", "dataTypes", "typeClasses", "instances", "imports", "templateHaskell"]
            elif language == "typescript":
                # For TypeScript: functions, classes, interfaces, types, enums, constants, fields
                component_names = ["functions", "classes", "interfaces", "types", "enums", "constants", "fields"]
            else:
                # Default mapping for other languages
                component_names = ["functions", "classes", "types", "variables", "imports", "constants"]
            
            for i, component_dict in enumerate(components):
                if i < len(component_names) and component_dict:
                    component_type = component_names[i]
                    result["components"][component_type] = []
                    for name, data in component_dict.items():
                        if isinstance(data, tuple) and len(data) >= 4:
                            result["components"][component_type].append({
                                "name": name,
                                "start_line": data[2][0] + 1,
                                "end_line": data[3][0] + 1,
                                "content": data[1],  # Full content instead of preview
                                "start_byte": data[2][1] if len(data[2]) > 1 else 0,
                                "end_byte": data[3][1] if len(data[3]) > 1 else 0
                            })
        
        return result
        
    except Exception as e:
        return {"error": f"Error processing file {file_path}: {str(e)}"}

def demo_with_sample_files():
    """Demonstrate extraction with sample files from the repository."""
    
    print("=== Demo: Extracting Top-Level Components from Single Files ===\n")
    
    # Sample files to test with - using the Haskell file from user feedback
    sample_files = [
      "/Users/pramod.p/euler-api-gateway/Setup.hs"  # Test the Haskell file with function signatures + implementations
    ]
    
    all_results = []
    
    for file_path in sample_files:
        print(f"--- Analyzing: {file_path} ---")
        
        if os.path.exists(file_path):
            result = extract_components_from_file(file_path)
            
            all_results.append(result)
            
            if "error" in result:
                print(f"❌ {result['error']}")
            else:
                print(f"✅ Language: {result['language']}")
                print(f"📁 Components found:")
                
                for component_type, items in result["components"].items():
                    print(f"  {component_type}: {len(items)} items")
                    for item in items:
                        print(f"    - {item['name']} (lines {item['start_line']}-{item['end_line']})")
        else:
            error_result = {"error": f"File not found: {file_path}", "file_path": file_path}
            all_results.append(error_result)
            print(f"❌ File not found: {file_path}")
        
        print()
    
    # Save results to JSON file
    output_file = "extracted_components.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"📄 Results saved to: {output_file}")
    except Exception as e:
        print(f"❌ Error saving to JSON: {str(e)}")

if __name__ == "__main__":
    demo_with_sample_files()
    