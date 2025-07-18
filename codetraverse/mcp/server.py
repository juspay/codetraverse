from fastmcp import FastMCP
from codetraverse.main import create_fdep_data
from codetraverse.mcp.helper import parsed_data, auto_mcp_tool, safe_error
import codetraverse.utils.blackbox as blackbox
from codetraverse.path import find_path

mcp = FastMCP(
    "Codetraverse MCP", instructions=parsed_data["tool_description"]["instructions"]
)


@auto_mcp_tool(mcp, "create_fdep_data")
@safe_error
def mcp_create_fdep_data(
    root_dir: str,
    fdep_output_path: str = "./output/fdep",
    graph_output_path: str = "./output/graph",
):
    create_fdep_data(root_dir, fdep_output_path, graph_output_path, clear_existing=True)
    return {
        "status": "success",
        "fdep_path": fdep_output_path,
        "graph_path": graph_output_path,
    }


@auto_mcp_tool(mcp, "get_component_details")
@safe_error
def mcp_get_component_details(
    fdep_folder: str,
    module_name: str,
    component_name: str,
):
    return blackbox.getFunctionInfo(fdep_folder, module_name, component_name)


@auto_mcp_tool(mcp, "get_component_children")
@safe_error
def mcp_get_component_children(
    graph_path: str, module_name: str, component_name: str, depth: int = 1
):
    return blackbox.getFunctionChildren(graph_path, module_name, component_name, depth)


@auto_mcp_tool(mcp, "find_lca")
def mcp_find_lca(
    graph_path: str,
    module_name1: str,
    component_name1: str,
    module_name2: str,
    component_name2: str,
):
    return blackbox.getCommonParents(
        graph_path, module_name1, component_name1, module_name2, component_name2
    )


@auto_mcp_tool(mcp, "get_common_children")
def mcp_get_common_children(
    graph_path: str,
    module_name1: str,
    component_name1: str,
    module_name2: str,
    component_name2: str,
):
    return blackbox.getCommonChildren(
        graph_path, module_name1, component_name1, module_name2, component_name2
    )


@auto_mcp_tool(mcp, "find_dependency_path")
def mcp_find_dependency_path(graph_path: str, from_component: str, to_component: str):
    return find_path(graph_path, from_component, to_component, return_obj=True)


@auto_mcp_tool(mcp, "list_components_in_module")
def mcp_list_components_in_modules(
    fdep_folder: str,
    module_name: str,
):
    return blackbox.getModuleInfo(fdep_folder, module_name)


@auto_mcp_tool(mcp, "get_surrounding_components")
def mcp_get_surrounding_components(
    graph_path: str,
    module_name: str,
    component_name: str,
    parent_depth: int = 1,
    child_depth: int = 1,
):
    return blackbox.getSubgraph(
        graph_path, module_name, component_name, parent_depth, child_depth
    )


if __name__ == "__main__":
    mcp.run(transport="sse")
