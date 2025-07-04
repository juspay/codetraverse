from codetraverse.main import create_fdep_data
from codetraverse.path import find_path

if __name__ == "__main__":
    create_fdep_data(
        # root_dir="/Users/suryansh.s/Tree-sitter/hyperswitch",
        # root_dir="/Users/suryansh.s/Euler/euler-api-txns",
        root_dir="/Users/suryansh.s/Xyne/code",
        output_base="fdep_xyne",
        graph_dir="graph_xyne",
        clear_existing=True
    )

# find_path(
#     graph_path="graph_txns/repo_function_calls.graphml",
#     component="Euler.API.Txns.Endpoints.EnabledGatewayList.Flow::enabledGatewayListHandler",
#     # source="Euler.API.Txns.Endpoints.EnabledGatewayList.Flow::getDeciderParams"
# )