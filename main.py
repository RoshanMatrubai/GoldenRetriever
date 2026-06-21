import argparse

from werkzeug.serving import make_server


def main():
    parser = argparse.ArgumentParser(
        description="GoldenRetriever — Scoped Access Broker for Agentic AI"
    )
    parser.add_argument("--mcp", action="store_true", help="Run as stdio MCP server")
    args = parser.parse_args()

    import config

    if args.mcp:
        print("GoldenRetriever MCP server starting (stdio)…", flush=True)
        return

    from agent.api import create_agent_app
    from agent.queue import RequestQueue

    queue = RequestQueue(config.DB_PATH)
    agent_app = create_agent_app(queue)

    print(
        f"GoldenRetriever — dashboard :{config.DASHBOARD_PORT}  "
        f"agent API :{config.AGENT_API_PORT}",
        flush=True,
    )
    print(f"[agent-api] listening on 0.0.0.0:{config.AGENT_API_PORT}", flush=True)

    # Phase 7 will move this into a thread and run SocketIO on the main thread
    server = make_server("0.0.0.0", config.AGENT_API_PORT, agent_app)
    server.serve_forever()


if __name__ == "__main__":
    main()
