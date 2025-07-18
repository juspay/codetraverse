from codetraverse.mcp.server import mcp
import codetraverse.mcp.server as server
from codetraverse.utils.blackbox import getAllModules

def main():
    # defaults to http://localhost:8000/sse
    mcp.run(transport="sse")
    # getAllModules("/Users/jignyas.s/Desktop/Juspay/codegen/codegen/output/graph/repo_function_calls.graphml")
    # print(server.mcp_get_component_details("OpenAIIntraction", "consolidateMuliReq", "/Users/jignyas.s/Desktop/Juspay/codegen/codegen/output/fdep"))


if __name__ == "__main__":
    main()
