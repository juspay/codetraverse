import tomllib
from typing import Annotated
from pydantic import Field
from fastmcp import FastMCP
from functools import wraps
import traceback


parsed_data = None
with open("codetraverse/mcp/tool_descriptions.toml", "rb") as f:
    parsed_data = tomllib.load(f)


def auto_mcp_tool(mcp: FastMCP, tool_key: str):
    def decorator(func):
        tool_data = parsed_data[tool_key]
        annotations = dict(func.__annotations__)

        for k, v in tool_data.items():
            if k == "description":
                continue
            if k in annotations:
                annotations[k] = Annotated[annotations[k], Field(description=v)]
            else:
                annotations[k] = Annotated[str, Field(description=v)]

        func.__annotations__ = annotations
        return mcp.tool(name=tool_key, description=tool_data["description"])(func)

    return decorator


def safe_error(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(traceback.format_exc())
            return {"status": "failure", "message": str(e)}

    return wrapper
