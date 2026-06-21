import argparse
import threading

from werkzeug.serving import make_server

import config


def _open_vault():
    from core.vault import Vault, VaultError
    try:
        return Vault.unlock(config.DB_PATH, config.VAULT_MASTER_PASSWORD)
    except VaultError:
        print("[vault] no existing vault found — creating new vault…", flush=True)
        return Vault.create(config.DB_PATH, config.VAULT_MASTER_PASSWORD)


def main():
    parser = argparse.ArgumentParser(
        description="GoldenRetriever — Scoped Access Broker for Agentic AI"
    )
    parser.add_argument("--mcp", action="store_true", help="Run as stdio MCP server")
    args = parser.parse_args()

    if args.mcp:
        print("GoldenRetriever MCP server starting (stdio)…", flush=True)
        return

    vault = _open_vault()

    from agent.api import create_agent_app
    from agent.queue import RequestQueue
    from dashboard.app import create_dashboard_app

    queue = RequestQueue(config.DB_PATH)
    dashboard_app, sio = create_dashboard_app(queue, vault)

    # Agent API runs on a separate port in a background thread
    agent_app = create_agent_app(queue)
    agent_server = make_server("0.0.0.0", config.AGENT_API_PORT, agent_app)
    agent_thread = threading.Thread(
        target=agent_server.serve_forever,
        name="gr-agent-api",
        daemon=True,
    )
    agent_thread.start()

    print(
        f"GoldenRetriever — dashboard :{config.DASHBOARD_PORT}  "
        f"agent API :{config.AGENT_API_PORT}",
        flush=True,
    )
    print(f"[dashboard] http://localhost:{config.DASHBOARD_PORT}", flush=True)
    print(f"[agent-api] http://localhost:{config.AGENT_API_PORT}", flush=True)

    # SocketIO (threading mode) blocks on the main thread
    sio.run(
        dashboard_app,
        host="0.0.0.0",
        port=config.DASHBOARD_PORT,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
