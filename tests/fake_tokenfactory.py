"""A stand-in for Token Factory, on 127.0.0.1, for the tests: the model list, and chat completions that
answer from a script (or from a recording a live run made with GRAPHENE_TOKENFACTORY_RECORD). It speaks
the same JSON as the real endpoint, so the client, the planner and the executor run unchanged against it,
in this process or in a subprocess that `graphene run` starts.

Each reply in the script is one of:
- a dict: the assistant's message (``{"content": ...}`` or ``{"tool_calls": [...]}``), usage made up;
  ``"_finish": "length"`` in it sets the finish reason (a reply cut off at the token limit);
- a (message, usage) pair;
- a callable taking the request body and returning either of those;
- an int: answer with that HTTP status instead (a 429, a 500).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


# Made-up ids in the shape the real list has; a non-Nemotron model and a "-fast" twin are there so that
# picking the Nemotron sizes out of the list is tested, not assumed.
def _model(id: str, created: int, prompt: str, completion: str) -> dict:
    return {"id": id, "created": created, "pricing": {"prompt": prompt, "completion": completion}}


MODELS = [
    _model("meta-llama/Llama-3.3-70B-Instruct", 1, "1e-7", "3e-7"),
    _model("nvidia/Nemotron-3-Nano-fake", 2, "5e-8", "2e-7"),
    _model("nvidia/Nemotron-3-Nano-fake-fast", 3, "1e-7", "4e-7"),
    _model("nvidia/Nemotron-3-Super-fake", 2, "2e-7", "8e-7"),
    _model("nvidia/Nemotron-3-Ultra-fake", 2, "6e-7", "2.4e-6"),
]


def call(name: str, **arguments) -> dict:
    """An assistant message that calls one tool, as a model sends it."""
    return {"content": None, "tool_calls": [{"id": f"call_{name}_{abs(hash(json.dumps(arguments))) % 10**8}",
            "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}  # fmt: skip


class Fake:
    def __init__(self, replies=(), models=MODELS):
        self.replies = list(replies)
        self.models = models
        self.requests: list[dict] = []
        self.lock = threading.Lock()

    @classmethod
    def replay(cls, recording: Path) -> Fake:
        """Answer with what a live run was answered, in order."""
        rows = [json.loads(line) for line in recording.read_text().splitlines() if line.strip()]
        return cls([(r["response"]["choices"][0]["message"], r["response"].get("usage") or {}) for r in rows])

    def __enter__(self) -> Fake:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # quiet
                pass

            def _send(self, code: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                if code == 429:
                    self.send_header("Retry-After", "0")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.headers.get("Authorization", "") != "Bearer fake-key":
                    return self._send(401, {"detail": "Couldn't authenticate. Reason: token is not present"})
                if self.path.startswith("/v1/models"):
                    return self._send(200, {"object": "list", "data": fake.models})
                self._send(404, {"detail": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if self.headers.get("Authorization", "") != "Bearer fake-key":
                    return self._send(401, {"detail": "Couldn't authenticate. Reason: invalid token"})
                with fake.lock:
                    fake.requests.append(body)
                    reply = fake.replies.pop(0) if fake.replies else {"content": "(the script ran out)"}
                if callable(reply):
                    reply = reply(body)
                if isinstance(reply, int):
                    return self._send(reply, {"detail": f"scripted {reply}"})
                message, usage = reply if isinstance(reply, tuple) else (reply, None)
                usage = usage or {"prompt_tokens": len(json.dumps(body["messages"])) // 4,
                                  "completion_tokens": len(json.dumps(message)) // 4}  # fmt: skip
                usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                message = dict(message)
                called = "tool_calls" if message.get("tool_calls") else "stop"
                finish = message.pop("_finish", None) or called
                if body.get("stream"):  # a harness (OpenCode, through the AI SDK) asks for server-sent events
                    return self._stream(body, message, usage, finish)
                choice = {"index": 0, "message": {"role": "assistant", **message}, "finish_reason": finish}
                self._send(200, {"id": "fake", "object": "chat.completion", "model": body.get("model"),
                                 "choices": [choice], "usage": usage})  # fmt: skip

            def _stream(self, body: dict, message: dict, usage: dict, finish: str) -> None:
                """The same answer as two chunks (the whole message, then the finish and the usage)."""
                delta = {"role": "assistant", **{k: v for k, v in message.items() if v is not None}}
                if delta.get("tool_calls"):
                    delta["tool_calls"] = [{"index": k, **c} for k, c in enumerate(delta["tool_calls"])]
                head = {"id": "fake", "object": "chat.completion.chunk", "model": body.get("model")}
                chunks = [
                    {**head, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {**head, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage},
                ]
                data = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1/"

    def env(self) -> dict[str, str]:
        return {"GRAPHENE_TOKENFACTORY_URL": self.url, "NEBIUS_API_KEY": "fake-key"}
