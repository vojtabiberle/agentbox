import json
import os
import threading
from unittest.mock import patch

import pytest

from agentbox.broker import Broker, BrokerPolicy
from agentbox.server import ServerPolicy, execute


@pytest.mark.skipif(
    not os.environ.get("AGENTBOX_SERVER_TEST_IMAGE"), reason="Set AGENTBOX_SERVER_TEST_IMAGE"
)
def test_real_claude_uses_broker_with_fake_model(tmp_path):
    root = tmp_path
    model = "claude-sonnet-4-6"
    policy = BrokerPolicy(
        socket=root / "proxy.sock",
        ledger=root / "budget.db",
        kill_file=root / "STOP",
        anthropic_secret="projects/test/secrets/model/versions/latest",
        model=model,
        daily_budget_cents=500,
        request_reservation_cents=100,
        github_repository="org/repo",
        github_secret="projects/test/secrets/github/versions/latest",
    )

    def upstream(host, path, headers, body=None, method="POST"):
        assert headers["x-api-key"] == "fake"
        if path.endswith("count_tokens"):
            return 200, b'{"input_tokens":20}', "application/json"
        message = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": "Offline review OK."}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 20, "output_tokens": 4},
        }
        if not body.get("stream"):
            return 200, json.dumps(message).encode(), "application/json"
        events = [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {**message, "content": [], "stop_reason": None},
                },
            ),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Offline review OK."},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 4},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
        return (
            200,
            "".join(
                f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events
            ).encode(),
            "text/event-stream",
        )

    with (
        Broker(policy) as broker,
        patch("agentbox.broker.read_secret", return_value="fake"),
        patch("agentbox.broker.request_json", side_effect=upstream),
    ):
        threading.Thread(target=broker.serve_forever, daemon=True).start()
        work = root / "work"
        work.mkdir()
        config = ServerPolicy(
            image=os.environ["AGENTBOX_SERVER_TEST_IMAGE"],
            workspace_root=work,
            broker_socket=policy.socket,
            timeout_seconds=40,
            kill_file=policy.kill_file,
            command=[
                "claude",
                "--print",
                "--output-format",
                "text",
                "--model",
                model,
                "--max-turns",
                "3",
                "--tools",
                "",
                "--disable-slash-commands",
            ],
        )
        try:
            result = execute(config, work, b"Reply with Offline review OK.")
            assert result.returncode == 0, result.output
            assert b"Offline review OK." in result.output
        finally:
            broker.shutdown()
