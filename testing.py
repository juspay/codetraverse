from codetraverse.main import create_fdep_data
if __name__ == "__main__":
    # Example usage of create_fdep_data function
    # Uncomment the line below to run the function with specified parameters
    # create_fdep_data(root_dir="path_to_your_project", output_base="fdep", graph_dir="graph", clear_existing=True)
    create_fdep_data(
#         # root_dir="/Users/siraj.shaik/Desktop/test_xyne/xyne",
        # root_dir="/Users/siraj.shaik/Desktop/AI_FRAMEWORKS/for_typescript/type_script_files/dense-app/ts-test-project",
#         # root_dir="/Users/siraj.shaik/juspay/euler/euler-api-gateway",
#         # root_dir="/Users/siraj.shaik/Desktop/AI_FRAMEWORKS/for_typescript/type_script_files/dense-app/mini-repo",
#         # root_dir="/Users/siraj.shaik/Desktop/folder_for_xyne_code/code",
#         # root_dir="/Users/siraj.shaik/Desktop/temp/hyperswitch-control-center",
        # root_dir="/Users/siraj.shaik/Desktop/purescript_integration/euler-ps",
        # root_dir="/Users/siraj.shaik/Desktop/purescript_integration/nammayatri",
        # root_dir="/Users/siraj.shaik/Desktop/test_xyne/xyne",
        root_dir= "/Users/siraj.shaik/Desktop/Juspay/jusplay",


        # output_base="fdep_typescript",
        # graph_dir="graph_typescript",
        output_base="fdep",
        graph_dir="graph",
        clear_existing=True,
)


# from codetraverse.utils.AstDifferOrchestrator import run_ast_diff_from_config

# hi = run_ast_diff_from_config({
#     "provider_type": "local",
#     "local" : {"repo_path": "/Users/pramod.p/newton-hs"},
#     "from_commit": "281b835b1fbb0ed3c84fde399ae5f3ad60802bfc",
#     "to_commit": "b5b3f7801aa1f19fc7a6436376fdc7a5f7dc19d8"
# })

# for i, j in enumerate(hi):
#     if i == 5:
#         print(type(j))
#         break
