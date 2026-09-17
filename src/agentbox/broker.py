"""Small Unix-socket egress broker; credentials and budgets stay outside workloads."""

from __future__ import annotations

import base64
import datetime
import http.client
import ipaddress
import json
import os
import re
import select
import socket
import socketserver
import sqlite3
import ssl
import subprocess
import threading
import time
import urllib.request
from contextlib import closing
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import click
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .exceptions import ConfigError
from .server import audit, server, trusted_file


class BrokerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    socket: Path = Path("/run/agentbox-broker/proxy.sock")
    control_socket: Path = Path("/run/agentbox-broker/control.sock")
    kill_file: Path = Path("/etc/agentbox/STOP")
    ledger: Path = Path("/var/lib/agentbox-broker/budget.sqlite")
    allowed_hosts: list[str] = Field(default_factory=list)
    anthropic_secret: str
    model: str = Field(pattern=r"^[a-zA-Z0-9._-]+$")
    daily_budget_cents: int = Field(gt=0)
    # Administrator-reviewed worst-case cost for this exact model/context/output limit.
    request_reservation_cents: int = Field(gt=0)
    max_output_tokens: int = Field(default=4096, gt=0, le=16384)
    max_input_tokens: int = Field(default=100000, gt=0)
    github_repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    github_secret: str
    github_app_id: int | None = Field(default=None, gt=0)
    github_installation_id: int | None = Field(default=None, gt=0)

    @field_validator("anthropic_secret", "github_secret")
    @classmethod
    def secret_resource(cls, value: str) -> str:
        if not re.fullmatch(
            r"projects/[A-Za-z0-9_-]+/secrets/[A-Za-z0-9_-]+/versions/(latest|[0-9]+)", value
        ):
            raise ValueError("Use a Secret Manager version resource, never a secret value")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def exact_hosts(cls, values: list[str]) -> list[str]:
        for host in values:
            if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}", host):
                raise ValueError("Use exact lowercase DNS hostnames; no wildcards or IPs")
            if host in {"api.anthropic.com", "api.github.com", "metadata.google.internal"}:
                raise ValueError("Credential endpoints cannot bypass broker API policy")
        return values


def read_secret(resource: str) -> str:
    request = urllib.request.Request(
        "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
    )
    # Explicitly ignore proxy environment for metadata and secret retrieval.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        token = json.load(response)["access_token"]
    request = urllib.request.Request(
        "https://secretmanager.googleapis.com/v1/" + resource + ":access",
        headers={"Authorization": "Bearer " + token},
    )
    with opener.open(request, timeout=15) as response:
        return (
            base64.b64decode(json.load(response)["payload"]["data"], validate=True).decode().strip()
        )


def request_json(
    host: str, path: str, headers: dict[str, str], body: Any = None, method: str = "POST"
) -> tuple[int, bytes, str]:
    connection = http.client.HTTPSConnection(host, timeout=30, context=ssl.create_default_context())
    try:
        payload = json.dumps(body).encode() if body is not None else None
        connection.request(method, path, payload, {**headers, "Content-Type": "application/json"})
        response = connection.getresponse()
        data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Upstream response too large")
        return response.status, data, response.getheader("Content-Type", "application/json")
    finally:
        connection.close()


def reserve_budget(policy: BrokerPolicy) -> None:
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    with closing(sqlite3.connect(policy.ledger, timeout=5)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS budget (day TEXT PRIMARY KEY, cents INTEGER NOT NULL)"
        )
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT cents FROM budget WHERE day=?", (today,)).fetchone()
        spent = row[0] if row else 0
        if spent + policy.request_reservation_cents > policy.daily_budget_cents:
            raise PermissionError("Daily model budget exhausted")
        db.execute(
            "INSERT INTO budget VALUES (?,?) ON CONFLICT(day) DO UPDATE SET cents=excluded.cents",
            (today, spent + policy.request_reservation_cents),
        )
    # Conservative reservation is never refunded (including upstream/client failures).
    audit("model_budget_reserved", cents=policy.request_reservation_cents, day=today)


def public_addresses(host: str) -> list[tuple[Any, ...]]:
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(
        (
            not ipaddress.ip_address(item[4][0]).is_global
            or ipaddress.ip_address(item[4][0]).is_multicast
        )
        for item in addresses
    ):
        raise PermissionError("Destination resolves to a non-public address")
    return addresses


def github_token(policy: BrokerPolicy) -> str:
    secret = read_secret(policy.github_secret)
    if policy.github_app_id is None and policy.github_installation_id is None:
        return secret  # Explicit development PAT mode; secret never reaches workload.
    if policy.github_app_id is None or policy.github_installation_id is None:
        raise ValueError("Both GitHub App IDs are required")

    def encoded(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    now = int(time.time())
    unsigned = (
        encoded(b'{"alg":"RS256","typ":"JWT"}')
        + "."
        + encoded(
            json.dumps(
                {"iat": now - 30, "exp": now + 300, "iss": str(policy.github_app_id)}
            ).encode()
        )
    )
    fd = os.memfd_create("agentbox-github-key", flags=0)
    try:
        os.write(fd, secret.encode())
        os.lseek(fd, 0, os.SEEK_SET)
        signature = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", f"/proc/self/fd/{fd}"],
            input=unsigned.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            pass_fds=(fd,),
            check=True,
            timeout=10,
        )
    finally:
        os.close(fd)
    jwt = unsigned + "." + encoded(signature.stdout)
    status, data, _ = request_json(
        "api.github.com",
        f"/app/installations/{policy.github_installation_id}/access_tokens",
        {"Authorization": "Bearer " + jwt, "User-Agent": "agentbox-broker"},
        {
            "repositories": [policy.github_repository.split("/")[1]],
            "permissions": {"contents": "read", "pull_requests": "write"},
        },
    )
    if status != 201:
        raise PermissionError("Cannot obtain repository-scoped GitHub installation token")
    return str(json.loads(data)["token"])


class Broker(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, policy: BrokerPolicy, *, controller: bool = False):
        self.policy = policy
        self.controller = controller
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(str(policy.control_socket if controller else policy.socket), Handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        audit("broker_connection_failed")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server: Broker

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Never log URLs, headers, prompts or upstream bodies.

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def reply(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def allowed(self) -> None:
        if self.server.policy.kill_file.exists():
            raise PermissionError("Kill switch active")

    def do_CONNECT(self) -> None:
        try:
            self.allowed()
            parsed = urlsplit("//" + self.path)
            if parsed.username or parsed.password or parsed.port != 443 or parsed.path:
                raise PermissionError("Only exact HTTPS destinations are allowed")
            host = parsed.hostname
            if host is None or host not in self.server.policy.allowed_hosts:
                raise PermissionError("Destination not allowed")
            addresses = public_addresses(host)
            family, kind, protocol, _, address = addresses[0]
            with socket.socket(family, kind, protocol) as upstream:
                upstream.settimeout(10)
                upstream.connect(address)  # Connect to the checked address, never resolve twice.
                self.send_response(200)
                self.end_headers()
                self.wfile.flush()
                audit("egress_allowed", host=host)
                peers = {self.connection: upstream, upstream: self.connection}
                deadline = time.monotonic() + 600
                while time.monotonic() < deadline:
                    self.allowed()
                    ready, _, _ = select.select(list(peers), [], [], 1)
                    for source in ready:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        peers[source].sendall(chunk)
        except (OSError, ValueError):
            audit("egress_denied")
            self.close_connection = True
            # No endpoint or exception details are reflected to callers.
            try:
                self.reply(403, b'{"error":"egress denied"}')
            except OSError:
                pass

    def body(self) -> dict[str, Any]:
        if (
            self.headers.get("Transfer-Encoding")
            or len(self.headers.get_all("Content-Length", [])) != 1
        ):
            raise ValueError("Exactly one Content-Length required")
        size = int(self.headers["Content-Length"])
        if not 0 < size <= 2 * 1024 * 1024:
            raise ValueError("Invalid body size")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise ValueError("Expected object")
        return value

    def do_POST(self) -> None:
        try:
            self.allowed()
            body = self.body()
            if self.path.startswith("/github/"):
                self.github("POST", body)
                return
            if self.path.split("?")[0] not in {"/v1/messages", "/v1/messages/count_tokens"}:
                raise PermissionError("Endpoint not allowed")
            policy = self.server.policy
            if body.get("model") != policy.model:
                raise PermissionError("Model not allowed")

            # No provider-side paid tools, URL fetches, caching or unreviewed beta features.
            def check(value: Any) -> None:
                if isinstance(value, dict):
                    if "cache_control" in value:
                        del value["cache_control"]
                    if value.get("type") in {"url", "image", "document"}:
                        raise PermissionError("Only text/tool inputs supported")
                    for item in value.values():
                        check(item)
                elif isinstance(value, list):
                    for item in value:
                        check(item)

            check(body)
            # Claude Code adds identity/context hints; neither is needed by this text-only gateway.
            body.pop("metadata", None)
            body.pop("context_management", None)
            output_config = body.get("output_config", {})
            if (
                not isinstance(output_config, dict)
                or set(output_config) - {"effort"}
                or output_config.get("effort", "medium") not in {"low", "medium", "high", "max"}
            ):
                raise PermissionError("Unsupported output configuration")
            if any(tool.get("type", "custom") != "custom" for tool in body.get("tools", [])):
                raise PermissionError("Provider-hosted tools are disabled")
            headers = {
                "x-api-key": read_secret(policy.anthropic_secret),
                "anthropic-version": "2023-06-01",
            }
            count_body = {
                key: body[key]
                for key in ("model", "messages", "system", "tools", "tool_choice")
                if key in body
            }
            status, counted, _ = request_json(
                "api.anthropic.com", "/v1/messages/count_tokens", headers, count_body
            )
            if status != 200 or json.loads(counted)["input_tokens"] > policy.max_input_tokens:
                raise PermissionError("Input token admission failed")
            if self.path.split("?")[0].endswith("count_tokens"):
                self.reply(200, counted)
                return
            tokens = body.get("max_tokens")
            if type(tokens) is not int or not 0 < tokens <= policy.max_output_tokens:
                raise PermissionError("Output token limit exceeded")
            allowed_keys = {
                "model",
                "messages",
                "system",
                "tools",
                "tool_choice",
                "max_tokens",
                "stream",
                "temperature",
                "top_p",
                "top_k",
                "stop_sequences",
                "thinking",
                "output_config",
            }
            if set(body) - allowed_keys:
                raise PermissionError("Unsupported model request options")
            reserve_budget(policy)
            self.allowed()
            # Buffer SSE in memory with a fixed ceiling; no provider response is written to disk.
            status, output, content_type = request_json(
                "api.anthropic.com", "/v1/messages", headers, body
            )
            self.reply(status, output, content_type)
            audit("model_request_finished", status=status)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            sqlite3.Error,
            subprocess.SubprocessError,
        ):
            self.reply(403, b'{"error":"request denied or upstream unavailable"}')
            audit("broker_request_denied")

    def github(self, method: str, body: dict[str, Any] | None = None) -> None:
        policy = self.server.policy
        if not self.server.controller:
            raise PermissionError("GitHub actions require the controller socket")
        path = self.path.removeprefix("/github")
        prefix = "/repos/" + policy.github_repository
        # Only pull enumeration/detail/diff and issue comments. Never merge or push code.
        allowed_get = re.fullmatch(
            re.escape(prefix) + r"/pulls(?:/[1-9][0-9]*)?(?:\?state=open&per_page=100)?", path
        )
        allowed_comments = re.fullmatch(
            re.escape(prefix) + r"/issues/[1-9][0-9]*/comments(?:\?per_page=100)?", path
        )
        if method == "GET" and not (allowed_get or allowed_comments):
            raise PermissionError("GitHub read endpoint denied")
        if method == "POST" and (
            not allowed_comments
            or body is None
            or set(body) != {"body"}
            or not isinstance(body["body"], str)
            or len(body["body"]) > 60000
        ):
            raise PermissionError("GitHub write endpoint denied")
        headers = {
            "Authorization": "Bearer " + github_token(policy),
            "User-Agent": "agentbox-broker",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.headers.get("Accept") == "application/vnd.github.diff":
            headers["Accept"] = "application/vnd.github.diff"
        status, data, content_type = request_json("api.github.com", path, headers, body, method)
        self.reply(status, data, content_type)
        audit("github_request", method=method, status=status)

    def do_GET(self) -> None:
        try:
            self.allowed()
            if not self.path.startswith("/github/"):
                raise PermissionError("Endpoint denied")
            self.github("GET")
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            self.reply(403, b'{"error":"request denied or upstream unavailable"}')


@server.command("broker")
@click.option("--policy", type=click.Path(path_type=Path), default="/etc/agentbox/broker.yaml")
def broker_main(policy: Path) -> None:
    try:
        config = BrokerPolicy.model_validate(yaml.safe_load(trusted_file(policy)))
    except (OSError, ValueError, yaml.YAMLError):
        raise ConfigError("Invalid administrator broker configuration") from None
    for endpoint in (config.socket, config.control_socket):
        if endpoint.exists():
            endpoint.unlink()  # RuntimeDirectory is exclusively owned by this service.
    with Broker(config) as broker, Broker(config, controller=True) as controller:
        for endpoint in (config.socket, config.control_socket):
            os.chmod(endpoint, 0o660)
        threading.Thread(target=controller.serve_forever, daemon=True).start()
        audit("broker_started")
        broker.serve_forever()
