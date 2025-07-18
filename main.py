from codetraverse.mcp.server import mcp

def main():
    # defaults to http://localhost:8000/sse
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
