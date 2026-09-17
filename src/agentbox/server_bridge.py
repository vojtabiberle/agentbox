"""Runs inside the networkless container; forwards loopback HTTP to a Unix capability."""

import os
import select
import socket
import socketserver
import subprocess
import sys
import threading


class Bridge(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.connect("/run/agentbox-broker.sock")
            peers = {self.request: upstream, upstream: self.request}
            while True:
                ready, _, _ = select.select(list(peers), [], [], 30)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    peers[source].sendall(data)


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Bridge) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        env = dict(os.environ)
        env.update(
            HTTP_PROXY=endpoint,
            HTTPS_PROXY=endpoint,
            http_proxy=endpoint,
            https_proxy=endpoint,
            NO_PROXY="127.0.0.1,localhost",
            no_proxy="127.0.0.1,localhost",
            ANTHROPIC_BASE_URL=endpoint,
            ANTHROPIC_AUTH_TOKEN="broker-managed",
            DISABLE_TELEMETRY="1",
            CLAUDE_CODE_MAX_OUTPUT_TOKENS="4096",
            DISABLE_ERROR_REPORTING="1",
            CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
        )
        sys.exit(subprocess.call(sys.argv[1:], env=env))
