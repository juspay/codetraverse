from codetraverse.main import create_fdep_data
if __name__ == "__main__":
    # Example usage of create_fdep_data function
    # Uncomment the line below to run the function with specified parameters
    # create_fdep_data(root_dir="path_to_your_project", output_base="fdep", graph_dir="graph", clear_existing=True)
    create_fdep_data(
        root_dir="/Users/siraj.shaik/Desktop/test_xyne/xyne",
        # root_dir="/Users/siraj.shaik/Desktop/AI_FRAMEWORKS/for_typescript/type_script_files/dense-app/ts-test-project",
        # root_dir="/Users/siraj.shaik/juspay/euler/euler-api-gateway",
        # root_dir="/Users/siraj.shaik/Desktop/AI_FRAMEWORKS/for_typescript/type_script_files/dense-app/mini-repo",
        # root_dir="/Users/siraj.shaik/Desktop/folder_for_xyne_code/code",

        
        output_base="fdep",
        graph_dir="graph",
        clear_existing=True,
)
