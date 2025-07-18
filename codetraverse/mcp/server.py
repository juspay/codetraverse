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
    result = blackbox.getFunctionInfo(fdep_folder, module_name, component_name)
    if len(result) > 0 and "function_calls" in result[0]:
        result[0]["function_calls"] = list(
            filter(
                lambda x: ("name" in x and "modules" in x)
                or ("type" in x and x["type"] == "lambda"),
                result[0]["function_calls"],
            )
        )
    return result


@auto_mcp_tool(mcp, "get_component_children")
@safe_error
def mcp_get_component_children(
    graph_path: str,
    module_name: str,
    component_name: str,
    depth: int = 1,
):
    return list(
        map(
            lambda x: x[0],
            blackbox.getFunctionChildren(
                graph_path, module_name, component_name, depth
            ),
        )
    )


@auto_mcp_tool(mcp, "find_lca")
@safe_error
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
@safe_error
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
@safe_error
def mcp_find_dependency_path(
    graph_path: str,
    from_component: str,
    to_component: str,
):
    result = find_path(graph_path, to_component, from_component, return_obj=True)
    if result and len(result) > 0:
        return {"path": " -> ".join(result)}
    return {"output": result}


@auto_mcp_tool(mcp, "list_components_in_module")
@safe_error
def mcp_list_components_in_modules(
    fdep_folder: str,
    module_name: str,
):
    result = blackbox.getModuleInfo(fdep_folder, module_name)
    return list(
        map(
            lambda x: {
                "kind": x.get("kind", "NO TYPE OF COMPONENT"),
                "name": x.get("name", "NO NAME AVAILABLE"),
            },
            result,
        )
    )


@auto_mcp_tool(mcp, "get_surrounding_components")
@safe_error
def mcp_get_surrounding_components(
    graph_path: str,
    module_name: str,
    component_name: str,
    parent_depth: int = 1,
    child_depth: int = 1,
):
    result = blackbox.getSubgraph(
        graph_path, module_name, component_name, parent_depth, child_depth
    )
    if result:
        return {"nodes": list(result.nodes), "edges": [(u, v) for u, v in result.edges]}
    return {"message": "Unable to get surrounding components"}


@auto_mcp_tool(mcp, "list_all_modules")
@safe_error
def mcp_list_all_modules(graph_path: str):
    return blackbox.getAllModules(graph_path)


if __name__ == "__main__":
    mcp.run(transport="sse")
